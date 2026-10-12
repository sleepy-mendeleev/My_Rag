<template>
  <div class="app-layout">
    <!-- 侧边栏 -->
    <aside class="sidebar">
      <div class="logo-area">
        <div class="logo-icon">🧠</div>
        <h1>RAG 智能助手</h1>
      </div>

      <div class="sidebar-content">
        <div class="section-title">知识库设置</div>
        
        <div class="upload-box">
          <el-upload
            class="upload-dragger"
            drag
            action="#"
            :auto-upload="false"
            multiple
            v-model:file-list="filesToUpload"
            :disabled="uploading"
            :on-change="handleFileChange"
            :on-remove="handleFileChange"
            :show-file-list="true"
            :limit="20"
            :on-exceed="handleExceed"
            ref="uploadRef"
          >
            <el-icon class="upload-icon"><UploadFilled /></el-icon>
            <div class="upload-text">
              <p>点击或拖拽多个文件至此</p>
              <span>支持 PDF、DOCX、TXT、CSV、XLSX、XLS，最多 20 个</span>
            </div>
          </el-upload>
        </div>

        <div class="form-group">
          <label>集合名称</label>
          <el-input 
            v-model="collectionName" 
            :disabled="uploading"
            placeholder="例如: agent_rag" 
            class="custom-input"
          >
            <template #prefix>
              <el-icon><Collection /></el-icon>
            </template>
          </el-input>
        </div>

        <el-button 
          type="primary" 
          class="action-btn upload-btn" 
          :loading="uploading" 
          @click="submitUpload"
        >
          {{ uploading ? `正在入库 ${uploadCompleted}/${uploadResults.length}` : '立即解析入库' }}
        </el-button>

        <div v-if="uploadResults.length" class="upload-results" aria-live="polite">
          <div v-for="item in uploadResults" :key="item.uid" class="upload-result-item">
            <span class="upload-result-name" :title="item.name">{{ item.name }}</span>
            <span :class="`upload-status-${item.state}`">{{ uploadStatusLabels[item.state] }}</span>
            <p v-if="item.error" class="upload-result-error">{{ item.error }}</p>
          </div>
          <p v-if="!uploading && filesToUpload.length" class="upload-result-hint">失败文件已保留，可再次点击入库重试。</p>
        </div>

        <el-button
          type="primary"
          class="action-btn vector-manage-btn"
          :disabled="vectorBusy"
          @click="openVectorManager"
        >
          <el-icon><Collection /></el-icon>
          <span>查看入库向量</span>
        </el-button>

        <div v-if="uploadSuccess" class="success-tip">
          <el-icon><CircleCheckFilled /></el-icon>
          <span>入库成功，快去提问吧！</span>
        </div>
      </div>

      <div class="sidebar-footer">
        <p>© 2024 MCP Agent System</p>
      </div>
    </aside>

    <!-- 主聊天区域 -->
    <main class="chat-main">
      <!-- 顶部导航 -->
      <header class="chat-header">
        <div class="header-info">
          <h2>智能问答</h2>
          <span class="status-badge">
            <span class="status-dot"></span>
            当前集合: {{ collectionName }}
          </span>
        </div>
        <div class="header-actions">
          <el-button circle icon="Delete" @click="clearHistory" title="清空对话" />
        </div>
      </header>

      <!-- 消息列表 -->
      <div class="messages-container" ref="messagesRef">
        <div v-if="messages.length === 0" class="welcome-screen">
          <div class="welcome-icon">👋</div>
          <h3>你好！我是你的专属知识助手</h3>
          <p>请在左侧上传文档，然后在这里向我提问。</p>
          <div class="feature-list">
            <div class="feature-item">
              <el-icon><Document /></el-icon>
              <span>文档解析</span>
            </div>
            <div class="feature-item">
              <el-icon><Search /></el-icon>
              <span>精准检索</span>
            </div>
            <div class="feature-item">
              <el-icon><ChatLineRound /></el-icon>
              <span>智能问答</span>
            </div>
          </div>
        </div>

        <transition-group name="message-fade">
          <div 
            v-for="(msg, index) in messages" 
            :key="index" 
            :class="['message-row', msg.role]"
          >
            <div class="avatar">
              <el-avatar :size="40" :icon="msg.role === 'user' ? User : Service" :class="msg.role" />
            </div>
            <div class="message-content">
              <div class="bubble" v-html="renderMarkdown(msg.content)"></div>
              
              <!-- 引用来源卡片 -->
              <div v-if="msg.sources && msg.sources.length > 0" class="sources-card">
                <div class="sources-header" @click="toggleSources(index)">
                  <el-icon><CollectionTag /></el-icon>
                  <span>参考依据 ({{ msg.sources.length }})</span>
                  <el-icon :class="['arrow', { rotated: msg.showSources }]"><ArrowDown /></el-icon>
                </div>
                <div v-show="msg.showSources" class="sources-list">
                  <div v-for="(source, sIndex) in msg.sources" :key="sIndex" class="source-item">
                    <div class="source-meta">
                      <span class="index">#{{ sIndex + 1 }}</span>
                      <span class="score">相似度: {{ (source.score * 100).toFixed(1) }}%</span>
                    </div>
                    <div class="source-text">{{ source.content }}</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </transition-group>

        <div v-if="thinking" class="message-row assistant thinking-row">
          <div class="avatar">
            <el-avatar :size="40" :icon="Service" class="assistant" />
          </div>
          <div class="message-content">
            <div class="bubble thinking-bubble">
              <span class="dot"></span><span class="dot"></span><span class="dot"></span>
            </div>
          </div>
        </div>
      </div>

      <!-- 输入区域 -->
      <div class="input-wrapper">
        <div class="input-box">
          <el-input
            v-model="inputQuery"
            placeholder="输入您的问题，按 Enter 发送..."
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 5 }"
            resize="none"
            class="chat-input"
            @keydown.enter.prevent="sendMessage"
          />
          <el-button 
            type="primary" 
            circle 
            class="send-btn"
            :disabled="!inputQuery.trim() || thinking"
            @click="sendMessage"
          >
            <el-icon><Position /></el-icon>
          </el-button>
        </div>
        <div class="input-footer">
          <span>按 Enter 发送，Shift + Enter 换行</span>
        </div>
      </div>
    </main>

    <el-dialog v-model="vectorDialogVisible" title="入库向量管理" width="min(1100px, 95vw)">
      <div class="vector-toolbar">
        <div class="vector-collection-picker">
          <span>集合</span>
          <el-select v-model="managedCollection" filterable placeholder="选择知识库集合"
                     :loading="collectionsLoading" :disabled="vectorBusy || !collectionOptions.length"
                     @change="changeManagedCollection">
            <el-option v-for="name in collectionOptions" :key="name" :label="name" :value="name" />
          </el-select>
        </div>
        <el-button :disabled="vectorBusy" @click="refreshVectorManager">刷新集合与向量</el-button>
      </div>
      <div class="vector-batch-toolbar">
        <span>每页 {{ vectorPageSize }} 条 · 当前页已选 {{ selectedVectorRows.length }} 条</span>
        <el-button type="danger" :disabled="vectorBusy || !selectedVectorRows.length"
                   @click="deleteVectorRows(selectedVectorRows)">删除选中向量</el-button>
      </div>
      <el-alert title="每条记录对应一个文本片段。删除后该片段将不再参与后续检索，已显示的聊天记录不会改变。"
                type="info" :closable="false" class="vector-notice" />
      <el-alert v-if="vectorLoadError" :title="vectorLoadError" type="error" :closable="false" />
      <el-table ref="vectorTableRef" v-loading="vectorsLoading" :data="vectorRows" row-key="id" max-height="440"
                @selection-change="selectedVectorRows = $event"
                :empty-text="vectorLoadError ? '加载失败，请重试' : (!collectionOptions.length ? '暂无知识库集合，请先上传文件' : '当前集合没有入库向量')">
        <el-table-column type="selection" width="45" :selectable="() => !vectorBusy" />
        <el-table-column prop="id" label="向量 ID" width="190" />
        <el-table-column prop="source" label="来源" min-width="170" show-overflow-tooltip />
        <el-table-column prop="content" label="文本片段" min-width="260">
          <template #default="{ row, column }">
            <el-tooltip placement="top" :disabled="!row.content"
                        :popper-style="{ width: `${column.realWidth || 260}px`, maxWidth: 'calc(100vw - 24px)', boxSizing: 'border-box' }">
              <template #content>
                <div class="vector-text-preview">{{ summarizeVectorText(row.content) }}</div>
              </template>
              <span class="vector-text-cell">{{ row.content }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column prop="dimension" label="维度" width="75" />
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="showVectorDetails(row)">详情</el-button>
            <el-button link type="danger" :loading="deletingVectorId === row.id"
                       :disabled="vectorBusy"
                       @click="deleteVectorRow(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="vector-pagination">
        <el-button :disabled="vectorOffset === 0 || vectorBusy || !managedCollection"
                   @click="loadVectors(vectorOffset - vectorPageSize)">上一页</el-button>
        <span>第 {{ Math.floor(vectorOffset / vectorPageSize) + 1 }} 页</span>
        <el-button :disabled="!vectorHasMore || vectorBusy"
                   @click="loadVectors(vectorOffset + vectorPageSize)">下一页</el-button>
      </div>
    </el-dialog>

    <el-dialog v-model="vectorDetailsVisible" title="向量详情" width="min(900px, 95vw)">
      <template v-if="selectedVector">
        <p>ID：{{ selectedVector.id }} · 维度：{{ selectedVector.dimension }}</p>
        <h4>文本片段</h4>
        <pre class="vector-detail-text">{{ selectedVector.content }}</pre>
        <h4>来源信息</h4>
        <pre class="vector-detail-text">{{ JSON.stringify(selectedVector.metadata, null, 2) }}</pre>
        <h4>完整向量</h4>
        <pre class="vector-detail-values">{{ JSON.stringify(selectedVector.vector, null, 2) }}</pre>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, nextTick, computed } from 'vue'
import { 
  UploadFilled, User, Service, Position, Collection, 
  CircleCheckFilled, Delete, Document, Search, ChatLineRound,
  CollectionTag, ArrowDown
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import axios from 'axios'
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({ html: true, breaks: true, linkify: true })
const API_BASE = 'http://localhost:5000/api/vector'

// State
const collectionName = ref('agent_rag')
const uploadRef = ref(null)
const filesToUpload = ref([])
const uploading = ref(false)
const uploadSuccess = ref(false)
const uploadResults = ref([])
const uploadCompleted = ref(0)
const uploadStatusLabels = { waiting: '等待', processing: '处理中', success: '成功', failure: '失败' }

const inputQuery = ref('')
const messages = ref([])
const thinking = ref(false)
const messagesRef = ref(null)

const vectorDialogVisible = ref(false)
const vectorDetailsVisible = ref(false)
const managedCollection = ref('')
const vectorRows = ref([])
const vectorsLoading = ref(false)
const vectorLoadError = ref('')
const vectorOffset = ref(0)
const vectorHasMore = ref(false)
const vectorPageSize = 10
const selectedVector = ref(null)
const deletingVectorId = ref('')
const collectionOptions = ref([])
const collectionsLoading = ref(false)
const selectedVectorRows = ref([])
const vectorTableRef = ref(null)
const vectorBusy = computed(() => uploading.value || vectorsLoading.value || collectionsLoading.value || !!deletingVectorId.value)

const resetVectorSelection = () => {
  selectedVectorRows.value = []
  vectorTableRef.value?.clearSelection()
}

// Hover shows a short preview; the detail dialog keeps the complete text.
const summarizeVectorText = (text) => {
  const clean = String(text || '').replace(/\s+/g, ' ').trim()
  const characters = Array.from(clean)
  return characters.length > 160 ? `${characters.slice(0, 160).join('')}…` : clean
}

const loadVectors = async (offset = 0) => {
  resetVectorSelection()
  selectedVector.value = null
  vectorDetailsVisible.value = false
  if (!managedCollection.value) {
    vectorRows.value = []
    vectorOffset.value = 0
    vectorHasMore.value = false
    return
  }
  vectorsLoading.value = true
  vectorLoadError.value = ''
  try {
    const { data } = await axios.get(`${API_BASE}/vectors`, {
      params: { collection_name: managedCollection.value, offset, limit: vectorPageSize },
      timeout: 30000
    })
    if (!data.success) throw new Error(data.message || '读取向量失败')
    vectorRows.value = data.items
    vectorOffset.value = offset
    vectorHasMore.value = data.has_more && offset + vectorPageSize * 2 + 1 < 16384
  } catch (error) {
    vectorRows.value = []
    vectorHasMore.value = false
    vectorLoadError.value = error.response?.data?.message || error.message || '读取向量失败'
  } finally {
    vectorsLoading.value = false
  }
}

const refreshVectorManager = async () => {
  collectionsLoading.value = true
  vectorLoadError.value = ''
  resetVectorSelection()
  try {
    const { data } = await axios.get(`${API_BASE}/collections`, { timeout: 30000 })
    if (!data.success) throw new Error(data.message || '读取集合列表失败')
    collectionOptions.value = data.collections
    if (!collectionOptions.value.includes(managedCollection.value)) {
      managedCollection.value = collectionOptions.value[0] || ''
    }
    if (managedCollection.value) collectionName.value = managedCollection.value
    await loadVectors(0)
  } catch (error) {
    vectorRows.value = []
    vectorHasMore.value = false
    vectorLoadError.value = error.response?.data?.message || error.message || '读取集合列表失败'
  } finally {
    collectionsLoading.value = false
  }
}

const changeManagedCollection = async () => {
  // Keep the visible upload/query collection in sync with the selected library.
  collectionName.value = managedCollection.value
  await loadVectors(0)
}

const openVectorManager = async () => {
  if (vectorBusy.value) return
  managedCollection.value = collectionName.value.trim()
  vectorRows.value = []
  vectorOffset.value = 0
  vectorDialogVisible.value = true
  await refreshVectorManager()
}

const showVectorDetails = (row) => {
  selectedVector.value = row
  vectorDetailsVisible.value = true
}

const deleteVectorRows = async (rows) => {
  if (vectorBusy.value || !rows.length) return
  const targetCollection = managedCollection.value
  const ids = rows.map(row => row.id)
  // Reserve the operation before confirmation to prevent simultaneous dialogs.
  deletingVectorId.value = ids.length === 1 ? ids[0] : 'batch'
  try {
    await ElMessageBox.confirm(
      `确定删除集合「${targetCollection}」中选中的 ${ids.length} 条向量吗？对应文本片段及其向量将被永久删除。`,
      '确认删除选中向量',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
    const { data } = await axios.post(`${API_BASE}/vectors/batch_delete`, {
      collection_name: targetCollection, vector_ids: ids
    }, { timeout: 30000 })
    if (!data.success) throw new Error(data.message || '删除失败')
    ElMessage.success(`已删除 ${data.deleted_ids.length} 条向量${data.missing_ids.length ? `，另有 ${data.missing_ids.length} 条已不存在` : ''}`)
    selectedVector.value = null
    vectorDetailsVisible.value = false
    await loadVectors(0)
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error.response?.data?.message || error.message || '删除失败，请刷新列表确认记录状态')
    }
  } finally {
    deletingVectorId.value = ''
  }
}

const deleteVectorRow = (row) => deleteVectorRows([row])

// Markdown 渲染
const renderMarkdown = (text) => {
  return md.render(text || '')
}

// Toggle Sources
const toggleSources = (index) => {
  const msg = messages.value[index]
  msg.showSources = !msg.showSources
}

// 清空历史
const clearHistory = () => {
  messages.value = []
}

// File Upload Logic
const handleFileChange = () => {
  uploadSuccess.value = false
  if (!uploading.value) uploadResults.value = []
}

const handleExceed = () => {
  ElMessage.warning('一次最多选择 20 个文件，请分批上传')
}

const submitUpload = async () => {
  if (uploading.value) return
  const files = filesToUpload.value.filter(file => file.raw)
  if (!files.length) {
    ElMessage.warning('请先选择文件')
    return
  }
  const targetCollection = collectionName.value.trim()
  if (!targetCollection) {
    ElMessage.warning('请填写集合名称')
    return
  }

  uploading.value = true
  uploadSuccess.value = false
  uploadCompleted.value = 0
  uploadResults.value = files.map(file => ({ uid: file.uid, name: file.name, state: 'waiting', error: '' }))
  const successfulIds = new Set()

  try {
    // Process one file at a time using the existing upload API.
    for (let index = 0; index < files.length; index++) {
      const file = files[index]
      const result = uploadResults.value[index]
      result.state = 'processing'
      try {
        const formData = new FormData()
        formData.append('file', file.raw)
        formData.append('collection_name', targetCollection)
        const { data } = await axios.post(`${API_BASE}/upload_file`, formData)
        if (!data.success) throw new Error(data.message || '文件入库失败')
        result.state = 'success'
        successfulIds.add(file.uid)
      } catch (error) {
        result.state = 'failure'
        result.error = error.response?.data?.message || error.message || '上传失败'
      } finally {
        uploadCompleted.value++
      }
    }
    uploadSuccess.value = successfulIds.size === files.length
    const message = `入库完成：成功 ${successfulIds.size} 个，失败 ${files.length - successfulIds.size} 个`
    if (uploadSuccess.value) ElMessage.success(message)
    else ElMessage.warning(message)
    // Remove only successful files, so retries do not duplicate their vectors.
    filesToUpload.value = filesToUpload.value.filter(file => !successfulIds.has(file.uid))
  } finally {
    uploading.value = false
  }
}

// Chat Logic
const sendMessage = async () => {
  const query = inputQuery.value.trim()
  if (!query || thinking.value) return
  
  messages.value.push({
    role: 'user',
    content: query
  })
  
  inputQuery.value = ''
  thinking.value = true
  scrollToBottom()

  try {
    const response = await axios.post(`${API_BASE}/query`, {
      question: query,
      collection_name: collectionName.value
    })

    if (response.data.success) {
      messages.value.push({
        role: 'assistant',
        content: response.data.answer,
        sources: response.data.sources,
        showSources: false // 默认折叠引用
      })
    } else {
       messages.value.push({
        role: 'assistant',
        content: '抱歉，我遇到了一些问题：' + response.data.message
      })
    }
  } catch (error) {
     messages.value.push({
        role: 'assistant',
        content: '网络错误或服务不可用，请检查后端服务是否启动。'
      })
  } finally {
    thinking.value = false
    scrollToBottom()
  }
}

const scrollToBottom = () => {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}
</script>

<style scoped>
.sidebar .el-button.vector-manage-btn {
  margin: 12px 0 0;
}

.upload-results {
  margin-top: 14px;
  max-height: 240px;
  overflow-y: auto;
  font-size: 12px;
  color: #ddd;
}

.upload-result-item {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 6px;
  padding: 8px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.upload-result-name {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upload-status-success { color: #95d475; }
.upload-status-failure, .upload-result-error { color: #f89898; }
.upload-status-processing { color: #79bbff; }
.upload-result-error, .upload-result-hint {
  width: 100%;
  margin: 0;
  overflow-wrap: anywhere;
}

.vector-toolbar,
.vector-batch-toolbar,
.vector-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 12px 0;
}

.vector-toolbar {
  flex-wrap: wrap;
}

.vector-collection-picker {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.vector-collection-picker .el-select {
  width: 240px;
  max-width: 65vw;
}

.vector-notice {
  margin-bottom: 12px;
}

.vector-text-cell {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.vector-text-preview {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  overflow: hidden;
  overflow-wrap: anywhere;
  white-space: normal;
}

.vector-detail-text,
.vector-detail-values {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 260px;
  overflow: auto;
  padding: 12px;
  margin: 8px 0 16px;
  background: #f5f7fa;
}

/* 全局布局 */
.app-layout {
  display: flex;
  height: 100vh;
  width: 100%;
  background-color: #f0f2f5;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
  overflow: hidden;
}

/* 侧边栏样式 */
.sidebar {
  width: 280px;
  flex-shrink: 0;
  background: #1a1c23; /* 深色背景 */
  color: #fff;
  display: flex;
  flex-direction: column;
  box-shadow: 4px 0 15px rgba(0, 0, 0, 0.1);
  z-index: 10;
  transition: all 0.3s ease;
}

.logo-area {
  padding: 30px 20px;
  display: flex;
  align-items: center;
  gap: 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.logo-icon {
  font-size: 28px;
}

.logo-area h1 {
  font-size: 20px;
  font-weight: 600;
  margin: 0;
  letter-spacing: 1px;
  background: linear-gradient(45deg, #409eff, #36cfc9);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.sidebar-content {
  flex: 1;
  padding: 20px;
  overflow-y: auto;
}

.section-title {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.4);
  margin-bottom: 15px;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.upload-box {
  margin-bottom: 20px;
}

/* 深度定制 Element Plus 上传组件 */
:deep(.el-upload-dragger) {
  background-color: rgba(255, 255, 255, 0.05) !important;
  border: 1px dashed rgba(255, 255, 255, 0.2) !important;
  border-radius: 12px !important;
  transition: all 0.3s;
}

:deep(.el-upload-dragger:hover) {
  border-color: #409eff !important;
  background-color: rgba(255, 255, 255, 0.08) !important;
}

.upload-icon {
  font-size: 40px;
  color: rgba(255, 255, 255, 0.5);
  margin-bottom: 10px;
}

.upload-text p {
  color: rgba(255, 255, 255, 0.8);
  margin: 0 0 5px 0;
  font-size: 14px;
}

.upload-text span {
  color: rgba(255, 255, 255, 0.4);
  font-size: 12px;
}

.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.7);
  margin-bottom: 8px;
}

:deep(.custom-input .el-input__wrapper) {
  background-color: rgba(255, 255, 255, 0.05);
  box-shadow: none;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
}

:deep(.custom-input .el-input__inner) {
  color: #fff;
}

.action-btn {
  width: 100%;
  height: 44px;
  font-size: 15px;
  border-radius: 8px;
  font-weight: 500;
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.3);
}

.success-tip {
  margin-top: 15px;
  padding: 10px;
  background: rgba(103, 194, 58, 0.15);
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #67c23a;
  font-size: 13px;
}

.sidebar-footer {
  padding: 20px;
  text-align: center;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.3);
  font-size: 12px;
}

/* 主区域样式 */
.chat-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: #f5f7fa;
  position: relative;
}

.chat-header {
  height: 70px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 30px;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.02);
}

.header-info h2 {
  margin: 0 0 5px 0;
  font-size: 18px;
  color: #303133;
}

.status-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #909399;
  background: #f4f4f5;
  padding: 2px 8px;
  border-radius: 12px;
}

.status-dot {
  width: 6px;
  height: 6px;
  background: #67c23a;
  border-radius: 50%;
}

.messages-container {
  flex: 1;
  min-height: 0;
  padding: 30px;
  overflow-y: auto;
  scroll-behavior: smooth;
}

/* 欢迎屏幕 */
.welcome-screen {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #909399;
}

.welcome-icon {
  font-size: 60px;
  margin-bottom: 20px;
}

.welcome-screen h3 {
  color: #303133;
  font-size: 24px;
  margin: 0 0 10px 0;
}

.feature-list {
  display: flex;
  gap: 20px;
  margin-top: 40px;
}

.feature-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 20px;
  background: #fff;
  border-radius: 12px;
  width: 100px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
  transition: transform 0.3s;
}

.feature-item:hover {
  transform: translateY(-5px);
}

.feature-item .el-icon {
  font-size: 24px;
  color: #409eff;
}

/* 消息气泡 */
.message-row {
  display: flex;
  gap: 15px;
  margin-bottom: 30px;
  max-width: 800px;
  margin-left: auto;
  margin-right: auto;
}

.message-row.user {
  flex-direction: row-reverse;
}

.avatar .el-avatar {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.avatar .assistant {
  background: linear-gradient(135deg, #36cfc9, #409eff);
}

.avatar .user {
  background: linear-gradient(135deg, #667eea, #764ba2);
}

.message-content {
  max-width: 80%;
}

.bubble {
  padding: 15px 20px;
  border-radius: 16px;
  font-size: 15px;
  line-height: 1.7;
  position: relative;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.user .bubble {
  background: #409eff;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.assistant .bubble {
  background: #fff;
  color: #303133;
  border-bottom-left-radius: 4px;
}

/* 引用源卡片 */
.sources-card {
  margin-top: 10px;
  background: #fff;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid #ebeef5;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.02);
}

.sources-header {
  padding: 10px 15px;
  background: #f9fafc;
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  transition: background 0.2s;
}

.sources-header:hover {
  background: #f0f2f5;
}

.sources-header .arrow {
  margin-left: auto;
  transition: transform 0.3s;
}

.sources-header .arrow.rotated {
  transform: rotate(180deg);
}

.sources-list {
  padding: 0 15px 15px 15px;
}

.source-item {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed #ebeef5;
}

.source-item:first-child {
  border-top: none;
}

.source-meta {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
  font-size: 12px;
}

.source-meta .index {
  color: #409eff;
  font-weight: bold;
}

.source-meta .score {
  color: #909399;
}

.source-text {
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
}

/* 输入区域 */
.input-wrapper {
  padding: 20px 30px 30px 30px;
  background: #fff; /* 或保持透明，看设计 */
  background: linear-gradient(to top, #f5f7fa 80%, rgba(245, 247, 250, 0) 100%);
  display: flex;
  flex-direction: column;
  align-items: center;
}

.input-box {
  width: 100%;
  max-width: 800px;
  position: relative;
  background: #fff;
  border-radius: 24px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  border: 1px solid #ebeef5;
  transition: all 0.3s;
}

.input-box:focus-within {
  box-shadow: 0 4px 24px rgba(64, 158, 255, 0.15);
  border-color: #409eff;
}

:deep(.chat-input .el-textarea__inner) {
  box-shadow: none;
  border: none;
  background: transparent;
  padding: 15px 50px 15px 20px; /* 右侧留出按钮空间 */
  font-size: 15px;
  resize: none;
}

.send-btn {
  position: absolute;
  right: 10px;
  bottom: 10px; /* 或 align with single line */
  width: 36px;
  height: 36px;
}

.input-footer {
  margin-top: 10px;
  font-size: 12px;
  color: #909399;
}

/* 思考动画 */
.thinking-bubble {
  padding: 10px 15px !important;
}

.thinking .dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: #909399;
  margin: 0 3px;
  animation: jump 1.4s infinite ease-in-out;
}

.thinking .dot:nth-child(1) { animation-delay: 0s; }
.thinking .dot:nth-child(2) { animation-delay: 0.2s; }
.thinking .dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes jump {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-6px); }
}

/* 消息过渡动画 */
.message-fade-enter-active,
.message-fade-leave-active {
  transition: all 0.4s ease;
}

.message-fade-enter-from,
.message-fade-leave-to {
  opacity: 0;
  transform: translateY(20px);
}

/* Markdown 样式适配 */
:deep(.bubble p) {
  margin: 0 0 8px 0;
}

:deep(.bubble p:last-child) {
  margin: 0;
}

:deep(.bubble ul), :deep(.bubble ol) {
  padding-left: 20px;
  margin: 8px 0;
}

:deep(.bubble code) {
  background: rgba(0, 0, 0, 0.1);
  padding: 2px 4px;
  border-radius: 4px;
  font-family: monospace;
}

.user :deep(.bubble code) {
  background: rgba(255, 255, 255, 0.2);
}
</style>
