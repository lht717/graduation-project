<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { get, post } from "@/api/client.js";
import { useAuthStore } from "@/stores/auth.js";

defineOptions({ name: "MessageView" });

const auth = useAuthStore();
const isAdmin = computed(() => auth.isAdmin);

const threads = ref([]);
const selectedThread = ref(null);
const loaded = ref(false);
const listError = ref("");
const statusText = ref("正在加载私信…");
const statusState = ref("loading");
const replyContent = ref("");
const replyStatusText = ref("");
const replyStatusState = ref("");
const sending = ref(false);
const messageBody = ref(null);
const availableRecipients = ref([]);
const composePickerOpen = ref(false);
const composeRecipient = ref("");
const composeError = ref("");

function formatDate(value) {
  if (!value) return "时间未知";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("zh-CN");
}

function messageSender(message) {
  return message.sender_username || message.sender || "未知发送人";
}

function messageRecipient(message) {
  return message.recipient_username || message.recipient || "未知接收人";
}

/** 普通用户：对方永远是「管理员」；管理员：对方为对应普通用户 */
function counterpartInfo(message) {
  const senderU = message.sender_username || message.sender || "";
  const recipientU = message.recipient_username || message.recipient || "";
  const senderD =
    message.sender_display_name ||
    message.sender_name ||
    (senderU === "admin" || message.sender === "管理员" ? "管理员" : message.sender || senderU);
  const recipientD =
    message.recipient_display_name ||
    (recipientU === "admin" || message.recipient === "管理员" ? "管理员" : message.recipient || recipientU);
  if (!isAdmin.value) {
    return { key: "admin", label: "管理员" };
  }
  const isOwn = senderU === auth.user.username;
  const otherU = isOwn ? recipientU : senderU;
  const otherD = isOwn ? recipientD : senderD;
  return { key: otherU || "admin", label: otherD || otherU || "用户" };
}

function isOwnMessage(message) {
  const senderUsername = messageSender(message);
  return (
    senderUsername === auth.user.username ||
    senderUsername === (auth.user.display_name || auth.user.nickname)
  );
}

function senderName(message) {
  if (isOwnMessage(message)) return auth.displayName;
  const senderUsername = messageSender(message);
  return (
    message.sender_display_name ||
    message.sender_name ||
    (senderUsername === "admin" ? "管理员" : message.sender || senderUsername)
  );
}

function threadPreview(thread) {
  if (thread.messages.length) {
    const last = thread.messages[thread.messages.length - 1];
    return last.content || last.body || "（无消息内容）";
  }
  return thread.draft ? "新对话 · 发送第一条消息后显示" : "暂无消息";
}

const messageTitle = computed(() => {
  if (selectedThread.value) return selectedThread.value.label;
  if (loaded.value && !threads.value.length) return "暂无私信";
  return "选择一条私信";
});

const messageParties = computed(() =>
  selectedThread.value ? `${auth.displayName} ⇄ ${selectedThread.value.label}` : ""
);

const messageDate = computed(() => {
  if (!selectedThread.value) return "";
  const list = selectedThread.value.messages;
  if (!list.length) return "暂无消息";
  const last = list[list.length - 1];
  return formatDate(last.created_at || last.timestamp);
});

const bodyPlaceholder = computed(() => {
  if (selectedThread.value?.draft) {
    return `这是与 ${selectedThread.value.label} 的新对话，输入内容并点击「发送」即可创建。`;
  }
  if (selectedThread.value) {
    return isAdmin.value
      ? `还没有消息。你可以在此向 ${selectedThread.value.label} 发送私信。`
      : "暂无消息。你可以在下方给管理员发送私信。";
  }
  if (loaded.value && !threads.value.length) {
    return isAdmin.value
      ? "还没有私信对话，点击左侧「新建私信」选择学生发起对话。"
      : "还没有私信对话，点击左侧「新建私信」给管理员发消息。";
  }
  return "从左侧选择对话，查看消息内容。";
});

const statusClass = computed(() =>
  statusState.value ? `status ${statusState.value}` : "status"
);
const replyStatusClass = computed(() =>
  replyStatusState.value ? `status ${replyStatusState.value}` : "status"
);
const replyPlaceholder = computed(() =>
  selectedThread.value
    ? isAdmin.value
      ? `输入要发送给 ${selectedThread.value.label} 的消息`
      : "输入要发送给管理员的消息"
    : "输入要发送的消息"
);

function setReplyStatus(message, state = "") {
  replyStatusText.value = message;
  replyStatusState.value = state;
}

function selectThread(thread) {
  selectedThread.value = thread;
  composePickerOpen.value = false;
  composeError.value = "";
  setReplyStatus("");
}

/** 只保留真实会话；发起第一条私信时临时创建一个草稿会话 */
function openDraft(key, label) {
  const existing = threads.value.find((thread) => thread.key === key && !thread.draft);
  if (existing) {
    selectThread(existing);
    return;
  }
  const draft = { key, label, messages: [], draft: true };
  threads.value = [draft, ...threads.value.filter((thread) => !thread.draft)];
  selectThread(draft);
}

function startCompose() {
  composeError.value = "";
  if (!isAdmin.value) {
    openDraft("admin", "管理员");
    return;
  }
  composePickerOpen.value = !composePickerOpen.value;
}

function cancelCompose() {
  composePickerOpen.value = false;
  composeError.value = "";
}

function confirmCompose() {
  const username = composeRecipient.value;
  if (!username) {
    composeError.value = "请先选择要联系的学生。";
    return;
  }
  const recipient = availableRecipients.value.find((item) => item.username === username);
  if (!recipient) {
    composeError.value = "收件人不存在，请刷新后重试。";
    return;
  }
  composeError.value = "";
  composeRecipient.value = "";
  openDraft(recipient.username, recipient.display_name || recipient.username);
}

async function loadMessages(preferredKey = selectedThread.value?.key) {
  statusText.value = "正在加载私信…";
  statusState.value = "loading";
  listError.value = "";
  try {
    const result = await get("/api/messages");
    if (!Array.isArray(result.messages)) throw new Error("私信列表格式不正确");
    availableRecipients.value = Array.isArray(result.available_recipients)
      ? result.available_recipients
      : [];
    // 刷新时保留尚未发出的草稿，避免已输入的内容被清掉
    const currentDraft = selectedThread.value?.draft ? selectedThread.value : null;
    // 只按真实消息分组，不再预置空对话
    const grouped = new Map();
    result.messages.forEach((message) => {
      const { key, label } = counterpartInfo(message);
      if (!grouped.has(key)) grouped.set(key, { key, label, messages: [] });
      grouped.get(key).messages.push(message);
    });
    const list = [...grouped.values()];
    list.forEach((thread) =>
      thread.messages.sort(
        (a, b) => new Date(a.created_at || a.timestamp || 0) - new Date(b.created_at || b.timestamp || 0)
      )
    );
    list.sort((a, b) => {
      const aDate = a.messages.at(-1)?.created_at || a.messages.at(-1)?.timestamp || "";
      const bDate = b.messages.at(-1)?.created_at || b.messages.at(-1)?.timestamp || "";
      return new Date(bDate) - new Date(aDate);
    });
    if (currentDraft && !list.some((thread) => thread.key === currentDraft.key)) {
      list.unshift(currentDraft);
    }
    threads.value = list;
    loaded.value = true;
    const activeThread = list.find((thread) => thread.key === preferredKey) || list[0];
    if (activeThread) selectThread(activeThread);
    else selectedThread.value = null;
    const realCount = list.filter((thread) => !thread.draft).length;
    statusText.value = realCount
      ? `私信加载成功，共 ${realCount} 个对话。`
      : "暂无私信对话，可点击「新建私信」发起对话。";
    statusState.value = "success";
    auth.markMessagesRead(result.messages);
  } catch (error) {
    statusText.value = `私信加载失败：${error.message}`;
    statusState.value = "error";
    listError.value = "无法加载私信，请稍后重试。";
  }
}

function onEnter(event) {
  if (event.shiftKey) return;
  event.preventDefault();
  if (!sending.value) void sendReply();
}

async function sendReply() {
  if (!selectedThread.value) return;
  const content = replyContent.value.trim();
  if (!content) {
    setReplyStatus("请输入消息内容。", "error");
    return;
  }
  sending.value = true;
  setReplyStatus("正在发送…", "loading");
  const threadKey = selectedThread.value.key;
  try {
    await post("/api/messages", {
      recipient: threadKey,
      subject: isAdmin.value ? `管理员私信：${selectedThread.value.label}` : "用户与管理员私信",
      content
    });
    replyContent.value = "";
    // loadMessages 会重建会话（草稿变为真实对话）并重置提示，成功提示放在其后
    await loadMessages(threadKey);
    setReplyStatus("消息发送成功。", "success");
  } catch (error) {
    setReplyStatus(`消息发送失败：${error.message}`, "error");
  } finally {
    sending.value = false;
  }
}

watch(selectedThread, async () => {
  await nextTick();
  if (messageBody.value) messageBody.value.scrollTop = messageBody.value.scrollHeight;
});

onMounted(() => {
  void loadMessages();
});
</script>

<template>
  <section id="messageView">
    <main class="container view-container">
      <header class="page-head"><p class="eyebrow">MESSAGES</p><h1>私信</h1><p>{{ isAdmin ? "仅显示已有消息往来的对话；联系新学生请点击「新建私信」。" : "仅显示已有消息往来的对话；你仅可与系统管理员私信。" }}</p></header>
      <p :class="statusClass" id="messagesStatus" role="status" aria-live="polite">{{ statusText }}</p>
      <section class="message-layout">
        <aside class="account-card">
          <div class="message-list-head">
            <h2>对话列表</h2>
            <div class="message-list-tools">
              <button class="btn btn-primary" type="button" @click="startCompose">＋ 新建私信</button>
              <button class="btn btn-outline" id="refreshMessages" type="button" @click="loadMessages()">刷新</button>
            </div>
          </div>
          <div v-if="composePickerOpen" class="message-compose-picker">
            <label for="composeRecipient">选择要联系的学生
              <select id="composeRecipient" v-model="composeRecipient">
                <option value="" disabled>请选择学生</option>
                <option v-for="recipient in availableRecipients" :key="recipient.username" :value="recipient.username">
                  {{ recipient.display_name || recipient.username }}（{{ recipient.username }}）
                </option>
              </select>
            </label>
            <p v-if="!availableRecipients.length" class="message-compose-error">暂无可联系的普通用户。</p>
            <p v-if="composeError" class="message-compose-error">{{ composeError }}</p>
            <div class="message-compose-actions">
              <button class="btn btn-outline" type="button" @click="cancelCompose">取消</button>
              <button class="btn btn-primary" type="button" :disabled="!availableRecipients.length" @click="confirmCompose">开始对话</button>
            </div>
          </div>
          <div id="messageList" class="message-list">
            <template v-if="listError">{{ listError }}</template>
            <template v-else>
              <button
                v-for="thread in threads"
                :key="thread.key"
                type="button"
                :class="['message-list-item', { 'message-list-draft': thread.draft }]"
                :data-thread-key="thread.key"
                :aria-pressed="selectedThread && selectedThread.key === thread.key ? 'true' : 'false'"
                @click="selectThread(thread)"
              ><strong>{{ thread.label }}</strong><span>{{ threadPreview(thread) }}</span></button>
              <p v-if="loaded && !threads.length" class="message-list-empty">
                暂无对话记录，点击上方「新建私信」{{ isAdmin ? "选择学生" : "联系管理员" }}发起对话。
              </p>
            </template>
          </div>
          <p v-if="!isAdmin" class="small-note" style="margin-top:10px">您仅能联系系统管理员。</p>
        </aside>
        <section class="account-card message-detail" aria-live="polite">
          <header class="message-conversation-head"><h2 id="messageTitle">{{ messageTitle }}</h2><p id="messageParties" class="view-description">{{ messageParties }}</p><p id="messageDate" class="view-description">{{ messageDate }}</p></header>
          <div id="messageBody" ref="messageBody" class="message-body" aria-label="聊天记录">
            <template v-if="selectedThread && selectedThread.messages.length">
              <article
                v-for="(message, index) in selectedThread.messages"
                :key="message.id || index"
                class="message-entry"
                :class="{ 'message-entry-own': isOwnMessage(message) }"
              >
                <div class="message-entry-meta"><strong>{{ senderName(message) }}</strong></div>
                <div class="message-bubble">{{ message.content || message.body || "（无消息内容）" }}</div>
                <time class="message-entry-time">{{ formatDate(message.created_at || message.timestamp) }}</time>
              </article>
            </template>
            <template v-else>{{ bodyPlaceholder }}</template>
          </div>
          <form id="replyForm" class="message-reply" :class="{ hidden: !selectedThread }" @submit.prevent="sendReply">
            <label class="sr-only" for="replyContent">发送消息</label>
            <textarea id="replyContent" v-model="replyContent" rows="2" maxlength="2000" required :placeholder="replyPlaceholder" @keydown.enter="onEnter"></textarea>
            <div class="message-reply-actions"><p :class="replyStatusClass" id="replyStatus" role="status" aria-live="polite">{{ replyStatusText }}</p><button class="btn btn-primary" type="submit" :disabled="sending">发送</button></div>
          </form>
        </section>
      </section>
    </main>
  </section>
</template>
