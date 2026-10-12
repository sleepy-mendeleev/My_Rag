import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { ref, computed, nextTick } from 'vue'

// Execute the actual component handlers with fake HTTP and UI; no real uploads.
function setup(post) {
  const source = readFileSync(new URL('../src/components/RagChat.vue', import.meta.url), 'utf8')
    .split('<script setup>')[1].split('</script>')[0]
    .replace(/^import[\s\S]*?from\s+['"][^'"]+['"]\s*\n/gm, '')
  const notices = []
  const context = {
    ref, computed, nextTick,
    axios: { post },
    ElMessage: { warning: value => notices.push(value), success: value => notices.push(value) },
    MarkdownIt: class { render(text) { return text } },
    FormData: class {
      constructor() { this.values = new Map() }
      append(key, value) { this.values.set(key, value) }
      get(key) { return this.values.get(key) }
    }
  }
  vm.runInNewContext(source + '\nglobalThis.uploader = { submitUpload, filesToUpload, collectionName, uploading, uploadResults, uploadCompleted };', context)
  return { ...context.uploader, notices }
}

const files = () => [1, 2, 3].map(uid => ({ uid, name: `${uid}.txt`, raw: { uid } }))

test('failure does not stop the batch, and retry includes only failed files', async () => {
  const calls = []
  const uploader = setup(async (_, form) => {
    const id = form.get('file').uid
    calls.push(id)
    if (id === 2 && calls.length === 2) throw new Error('bad file')
    return { data: { success: true } }
  })
  uploader.filesToUpload.value = files()
  await uploader.submitUpload()
  assert.deepEqual(calls, [1, 2, 3])
  assert.deepEqual(Array.from(uploader.uploadResults.value, item => item.state), ['success', 'failure', 'success'])
  assert.deepEqual(Array.from(uploader.filesToUpload.value, item => item.uid), [2])
  await uploader.submitUpload()
  assert.deepEqual(calls, [1, 2, 3, 2])
  assert.equal(uploader.filesToUpload.value.length, 0)
})

test('the collection is captured for the entire batch', async () => {
  const targets = []
  const uploader = setup(async (_, form) => {
    targets.push(form.get('collection_name'))
    uploader.collectionName.value = 'another_collection'
    return { data: { success: true } }
  })
  uploader.collectionName.value = 'bank_rag_v2'
  uploader.filesToUpload.value = files()
  await uploader.submitUpload()
  assert.deepEqual(targets, ['bank_rag_v2', 'bank_rag_v2', 'bank_rag_v2'])
})

test('a second click during upload does not send duplicate requests', async () => {
  let finish
  let calls = 0
  const uploader = setup(() => {
    calls++
    return new Promise(resolve => { finish = () => resolve({ data: { success: true } }) })
  })
  uploader.filesToUpload.value = files().slice(0, 1)
  const pending = uploader.submitUpload()
  await uploader.submitUpload()
  assert.equal(calls, 1)
  finish()
  await pending
  assert.equal(uploader.uploading.value, false)
})
