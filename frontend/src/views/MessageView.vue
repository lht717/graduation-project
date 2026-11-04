<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { get, post } from "@/api/client.js";
import { useAuthStore } from "@/stores/auth.js";
import AppTopbar from "@/components/AppTopbar.vue";

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
  return isAdmin.value ? `向 ${thread.label} 发起对话` : "点击此处给管理员发送私信";
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
  if (selectedThread.value) {
    return isAdmin.value
      ? `还没有消息。你可以在此向 ${selectedThread.value.label} 发送私信。`
      : "暂无消息。你可以在下方给管理员发送私信。";
  }
  if (loaded.value && !threads.value.length) {
    return isAdmin.value ? "还没有用户联系你，可等待用户发起对话。" : "当前没有私信。";
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
  setReplyStatus("");
}

async function loadMessages(preferredKey = selectedThread.value?.key) {
  statusText.value = "正在加载私信…";
  statusState.value = "loading";
  listError.value = "";
  try {
    const result = await get("/api/messages");
    if (!Array.isArray(result.messages)) throw new Error("私信列表格式不正确");
    const grouped = new Map();
    result.messages.forEach((message) => {
      const { key, label } = counterpartInfo(message);
      if (!grouped.has(key)) grouped.set(key, { key, label, messages: [] });
      grouped.get(key).messages.push(message);
    });
    if (!isAdmin.value && !grouped.has("admin")) {
      grouped.set("admin", { key: "admin", label: "管理员", messages: [] });
    }
    if (isAdmin.value && Array.isArray(result.available_recipients)) {
      result.available_recipients.forEach((recipient) => {
        if (!grouped.has(recipient.username)) {
          grouped.set(recipient.username, {
            key: recipient.username,
            label: recipient.display_name || recipient.username,
            messages: []
          });
        }
      });
    }
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
    threads.value = list;
    loaded.value = true;
    const activeThread = list.find((thread) => thread.key === preferredKey) || list[0];
    if (activeThread) selectThread(activeThread);
    else selectedThread.value = null;
    statusText.value = `私信加载成功，共 ${list.length} 个对话。`;
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
    setReplyStatus("消息发送成功。", "success");
    await loadMessages(threadKey);
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
    <AppTopbar variant="page" active="message" />
    <main class="container view-container">
      <header class="page-head"><p class="eyebrow">MESSAGES</p><h1>私信</h1><p>{{ isAdmin ? "管理员可向任意普通用户收发私信。" : "普通用户仅可与系统管理员对话，用户之间不可互相私信。" }}</p></header>
      <p :class="statusClass" id="messagesStatus" role="status" aria-live="polite">{{ statusText }}</p>
      <section class="message-layout">
        <aside class="account-card">
          <div class="message-list-head"><h2>对话列表</h2><button class="btn btn-outline" id="refreshMessages" @click="loadMessages()">刷新</button></div>
          <div id="messageList" class="message-list">
            <template v-if="listError">{{ listError }}</template>
            <template v-else>
              <button
                v-for="thread in threads"
                :key="thread.key"
                type="button"
                class="message-list-item"
                :data-thread-key="thread.key"
                :aria-pressed="selectedThread && selectedThread.key === thread.key ? 'true' : 'false'"
                @click="selectThread(thread)"
              ><strong>{{ thread.label }}</strong><span>{{ threadPreview(thread) }}</span></button>
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
