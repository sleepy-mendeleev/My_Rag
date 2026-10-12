"""
API集成模块
将向量数据库功能集成到Flask应用中
"""

from flask import Blueprint, request, jsonify
import os
import logging
import tempfile
from typing import Dict, Any, List
from werkzeug.utils import secure_filename
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parents[2] / '.env'
load_dotenv(dotenv_path=env_path)

from .vector_db_manager import VectorDatabaseManager
from .vector_retriever import VectorRetriever
from .document_loader import DocumentLoader

# 创建蓝图
vector_bp = Blueprint('vector', __name__, url_prefix='/api/vector')

# 全局变量存储向量系统实例
vector_manager: VectorDatabaseManager = None
vector_retriever: VectorRetriever = None

# 临时上传目录
UPLOAD_FOLDER = '/tmp/vector_uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_vector_system(
    milvus_host: str = None,
    milvus_port: str = None,
    embedding_model: str = None,
    dashscope_api_key: str = None
):
    """初始化向量系统"""
    global vector_manager, vector_retriever
    
    try:
        vector_manager = VectorDatabaseManager(
            milvus_host=milvus_host,
            milvus_port=milvus_port,
            embedding_model=embedding_model,
            dashscope_api_key=dashscope_api_key
        )
        vector_retriever = VectorRetriever(vector_manager)
        logger.info(f"向量系统初始化成功，连接到 Milvus at {milvus_host}:{milvus_port}")
        return True
    except Exception as e:
        logger.error(f"向量系统初始化失败: {str(e)}")
        return False


@vector_bp.route('/upload_document', methods=['POST'])
def upload_document():
    """上传并处理文档"""
    global vector_manager
    
    if not vector_manager:
        return jsonify({
            'success': False,
            'message': '向量系统未初始化'
        }), 400
    
    try:
        data = request.get_json()
        if not data or 'file_path' not in data or 'collection_name' not in data:
            return jsonify({
                'success': False,
                'message': '请提供 file_path 和 collection_name 参数'
            }), 400
        
        file_path = data['file_path']
        collection_name = data['collection_name']
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            return jsonify({
                'success': False,
                'message': f'文件不存在: {file_path}'
            }), 400
        
        # 处理文档
        success = vector_manager.process_file(file_path, collection_name)
        
        if success:
            # 获取数据库信息
            db_info = vector_manager.get_database_info(collection_name)
            
            return jsonify({
                'success': True,
                'message': f'文档处理成功: {file_path}',
                'database_info': db_info
            })
        else:
            return jsonify({
                'success': False,
                'message': f'文档处理失败: {file_path}'
            }), 500
            
    except Exception as e:
        logger.error(f"文档上传API错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'文档处理失败: {str(e)}'
        }), 500


@vector_bp.route('/upload_file', methods=['POST'])
def upload_file():
    """上传文件流处理"""
    global vector_manager
    
    if not vector_manager:
        return jsonify({'success': False, 'message': '向量系统未初始化'}), 400

    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '未找到文件部分'}), 400
        
    file = request.files['file']
    collection_name = request.form.get('collection_name', 'agent_rag')
    
    if file.filename == '':
        return jsonify({'success': False, 'message': '未选择文件'}), 400
        
    if file:
        try:
            vector_manager._validate_collection_name(collection_name)
            original_name = file.filename.replace(chr(92), '/').rsplit('/', 1)[-1]
            extension = Path(original_name).suffix.lower()
            if extension not in DocumentLoader.SUPPORTED_EXTENSIONS:
                return jsonify(success=False, message=f'暂不支持文件类型：{extension or "无扩展名"}'), 400
            filename = secure_filename(original_name)
            if not filename or Path(filename).suffix.lower() != extension:
                filename = f'document{extension}'
            # Isolate uploads so files with the same name never overwrite one another.
            directory = tempfile.mkdtemp(prefix='upload_', dir=UPLOAD_FOLDER)
            file_path = os.path.join(directory, filename)
            file.save(file_path)
            success = vector_manager.process_file(file_path, collection_name, file_name=original_name)
            if success:
                db_info = vector_manager.get_database_info(collection_name)
                return jsonify({
                    'success': True,
                    'message': f'文件上传并处理成功: {original_name}',
                    'database_info': db_info
                })
            else:
                 return jsonify({'success': False, 'message': '文件处理失败'}), 500
        except ValueError as e:
             return jsonify({'success': False, 'message': str(e)}), 400
        except Exception as e:
             return jsonify({'success': False, 'message': str(e)}), 500
        finally:
            # 可选：处理完后删除临时文件，或者保留
            # os.remove(file_path)
            pass

    return jsonify({'success': False, 'message': '上传失败'}), 500


@vector_bp.route('/query', methods=['POST'])
def query_documents():
    """查询文档"""
    global vector_retriever
    
    if not vector_retriever:
        return jsonify({
            'success': False,
            'message': '向量系统未初始化'
        }), 400
    
    try:
        data = request.get_json()
        if not data or 'question' not in data or 'collection_name' not in data:
            return jsonify({
                'success': False,
                'message': '请提供 question 和 collection_name 参数'
            }), 400
        
        question = data['question']
        collection_name = data['collection_name']
        k = data.get('k', 5)  # 返回结果数量
        
        # 执行查询
        result = vector_retriever.answer_question(question, k=k, collection_name=collection_name)
        
        return jsonify({
            'success': result.status != 'error',
            'request_id': result.request_id,
            'status': result.status,
            'message': result.answer if result.status == 'error' else '',
            'question': question,
            'answer': result.answer,
            'confidence': result.confidence,
            'question_type': result.question_type,
            'sources': [
                {
                    'content': doc.page_content,
                    'metadata': doc.metadata,
                    'score': score
                }
                for doc, score in zip(result.source_documents, result.scores)
            ]
        })
        
    except Exception as e:
        logger.error(f"查询API错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'查询失败: {str(e)}'
        }), 500


@vector_bp.route('/search', methods=['POST'])
def search_similar():
    """相似性搜索"""
    global vector_retriever
    
    if not vector_retriever:
        return jsonify({
            'success': False,
            'message': '向量系统未初始化'
        }), 400
    
    try:
        data = request.get_json()
        if not data or 'query' not in data or 'collection_name' not in data:
            return jsonify({
                'success': False,
                'message': '请提供 query 和 collection_name 参数'
            }), 400
        
        query = data['query']
        collection_name = data['collection_name']
        k = data.get('k', 5)
        
        # 执行相似性搜索
        results = vector_retriever.search_similar_content(query, k=k, collection_name=collection_name)
        
        return jsonify({
            'success': True,
            'query': query,
            'results': [
                {
                    'content': doc.page_content,
                    'metadata': doc.metadata,
                    'score': score
                }
                for doc, score in results
            ]
        })
        
    except Exception as e:
        logger.error(f"搜索API错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'搜索失败: {str(e)}'
        }), 500


@vector_bp.route('/collection_info', methods=['GET'])
def get_collection_info():
    """获取集合信息"""
    global vector_manager
    
    if not vector_manager:
        return jsonify({
            'success': False,
            'message': '向量系统未初始化'
        }), 400
    
    collection_name = request.args.get('collection_name')
    if not collection_name:
        return jsonify({
            'success': False,
            'message': '请提供 collection_name 参数'
        }), 400

    try:
        db_info = vector_manager.get_database_info(collection_name)
        return jsonify({
            'success': True,
            'database_info': db_info
        })
        
    except Exception as e:
        logger.error(f"数据库信息API错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'获取数据库信息失败: {str(e)}'
        }), 500


@vector_bp.route('/vectors', methods=['GET'])
def list_vectors():
    if vector_manager is None:
        return jsonify(success=False, message='向量系统未初始化'), 503
    try:
        collection_name = request.args.get('collection_name', '')
        offset = int(request.args.get('offset', '0'))
        limit = int(request.args.get('limit', '10'))
        result = vector_manager.list_vectors(collection_name, offset=offset, limit=limit)
        return jsonify(success=True, collection_name=collection_name, **result)
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    except Exception:
        logger.exception('读取向量列表失败')
        return jsonify(success=False, message='读取向量列表失败，请检查后端日志'), 500


@vector_bp.route('/collections', methods=['GET'])
def list_collections():
    if vector_manager is None:
        return jsonify(success=False, message='向量系统未初始化'), 503
    try:
        return jsonify(success=True, collections=vector_manager.list_collections())
    except Exception:
        logger.exception('读取集合列表失败')
        return jsonify(success=False, message='读取集合列表失败，请检查后端日志'), 500


@vector_bp.route('/vectors/batch_delete', methods=['POST'])
def delete_vectors():
    if vector_manager is None:
        return jsonify(success=False, message='向量系统未初始化'), 503
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValueError('请提交包含 collection_name 和 vector_ids 的 JSON 对象')
        result = vector_manager.delete_vectors(data.get('collection_name', ''), data.get('vector_ids'))
        return jsonify(success=True, **result)
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    except Exception:
        logger.exception('批量删除向量失败')
        return jsonify(success=False, message='批量删除失败，请刷新列表核对记录状态'), 500


@vector_bp.route('/vectors/<vector_id>', methods=['DELETE'])
def delete_vector(vector_id):
    if vector_manager is None:
        return jsonify(success=False, message='向量系统未初始化'), 503
    try:
        collection_name = request.args.get('collection_name', '')
        deleted = vector_manager.delete_vector(collection_name, vector_id)
        if not deleted:
            return jsonify(success=False, message='向量不存在或已经删除'), 404
        return jsonify(success=True, message='向量及其文本片段已删除', id=vector_id)
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    except Exception:
        logger.exception('删除向量失败')
        return jsonify(success=False, message='删除向量失败，请检查后端日志'), 500


@vector_bp.route('/clear_collection', methods=['POST'])
def clear_collection():
    """清空集合"""
    global vector_manager
    
    if not vector_manager:
        return jsonify({
            'success': False,
            'message': '向量系统未初始化'
        }), 400
    
    data = request.get_json()
    if not data or 'collection_name' not in data:
        return jsonify({
            'success': False,
            'message': '请提供 collection_name 参数'
        }), 400

    collection_name = data['collection_name']

    try:
        vector_manager.clear_database(collection_name)
        return jsonify({
            'success': True,
            'message': f"集合 '{collection_name}' 已清空"
        })
        
    except Exception as e:
        logger.error(f"清空数据库API错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'清空数据库失败: {str(e)}'
        }), 500


# 错误处理
@vector_bp.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'message': '接口不存在'
    }), 404


@vector_bp.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'message': '服务器内部错误'
    }), 500


def register_vector_routes(app):
    """注册向量数据库路由到Flask应用"""
    app.register_blueprint(vector_bp)
    
    # 自动初始化向量系统
    with app.app_context():
        init_vector_system()
    
    logger.info("向量数据库API路由已注册")
