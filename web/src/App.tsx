import {
  FormEvent,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import donateQr from "./Rickrolling_QR_code.png";

type MessageRole = "assistant" | "system" | "user";

type Message = {
  id: number;
  role: MessageRole;
  text: string;
};

type Conversation = {
  id: string;
  title: string;
  messages: Message[];
  updatedAt: number;
};

const initialMessages: Message[] = [
  {
    id: 1,
    role: "assistant",
    text: "Hỏi nhanh con mẹ mày lên",
  },
];

const CURRENT_CONVERSATION_KEY = "rag-law-vn.current-conversation";
const SAVED_CONVERSATIONS_KEY = "rag-law-vn.saved-conversations";
const LEGACY_HISTORY_KEY = "rag-law-vn.chat-history";
const HISTORY_BATCH_SIZE = 100;
const DEFAULT_CONVERSATION_TITLE = "Cuoc hoi thoai moi";

function createId() {
  return `conv-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function createConversation(messages: Message[] = initialMessages): Conversation {
  return {
    id: createId(),
    title: DEFAULT_CONVERSATION_TITLE,
    messages,
    updatedAt: Date.now(),
  };
}

function buildConversationTitle(messages: Message[]) {
  const firstUserMessage = messages.find((message) => message.role === "user");

  if (!firstUserMessage) {
    return DEFAULT_CONVERSATION_TITLE;
  }

  const compact = firstUserMessage.text.replace(/\s+/g, " ").trim();
  if (compact.length <= 36) {
    return compact;
  }

  return `${compact.slice(0, 36).trimEnd()}...`;
}

function isMessage(value: unknown): value is Message {
  return Boolean(
    value &&
      typeof value === "object" &&
      typeof (value as Message).id === "number" &&
      typeof (value as Message).text === "string" &&
      ((value as Message).role === "assistant" ||
        (value as Message).role === "system" ||
        (value as Message).role === "user"),
  );
}

function normalizeConversation(value: unknown): Conversation | null {
  if (!value || typeof value !== "object") {
    return null;
  }

  const conversation = value as Partial<Conversation>;
  if (
    typeof conversation.id !== "string" ||
    typeof conversation.title !== "string" ||
    typeof conversation.updatedAt !== "number" ||
    !Array.isArray(conversation.messages)
  ) {
    return null;
  }

  const messages = conversation.messages.filter(isMessage);
  return {
    id: conversation.id,
    title: conversation.title,
    messages: messages.length > 0 ? messages : initialMessages,
    updatedAt: conversation.updatedAt,
  };
}

function loadCurrentConversation() {
  const currentRaw = localStorage.getItem(CURRENT_CONVERSATION_KEY);
  if (currentRaw) {
    try {
      const parsed = normalizeConversation(JSON.parse(currentRaw));
      if (parsed) {
        return parsed;
      }
    } catch {
      // fall through
    }
  }

  return createConversation();
}

function loadSavedConversations() {
  const savedRaw = localStorage.getItem(SAVED_CONVERSATIONS_KEY);
  if (savedRaw) {
    try {
      const parsed = JSON.parse(savedRaw) as unknown;
      if (Array.isArray(parsed)) {
        const conversations = parsed
          .map(normalizeConversation)
          .filter((conversation): conversation is Conversation => conversation !== null);
        if (conversations.length > 0) {
          return conversations;
        }
      }
    } catch {
      // fall through
    }
  }

  const legacyRaw = localStorage.getItem(LEGACY_HISTORY_KEY);
  if (legacyRaw) {
    try {
      const parsed = JSON.parse(legacyRaw) as unknown;
      if (Array.isArray(parsed)) {
        const legacyMessages = parsed.filter(isMessage);
        if (legacyMessages.length > 0) {
          return [
            {
              id: createId(),
              title: buildConversationTitle(legacyMessages),
              messages: legacyMessages,
              updatedAt: Date.now(),
            },
          ];
        }
      }
    } catch {
      // fall through
    }
  }

  return [];
}

function formatConversationTime(updatedAt: number) {
  return new Date(updatedAt).toLocaleString("vi-VN");
}

function getConversationPreview(conversation: Conversation) {
  const lastMessage = conversation.messages[conversation.messages.length - 1];
  if (!lastMessage) {
    return "Chua co tin nhan.";
  }

  const compact = lastMessage.text.replace(/\s+/g, " ").trim();
  return compact.length <= 80 ? compact : `${compact.slice(0, 80).trimEnd()}...`;
}

async function sendQuestion(question: string) {
  const apiUrl = import.meta.env.VITE_CHAT_API_URL;

  if (!apiUrl) {
    return {
      text: "Chua cau hinh API. Hay dat bien moi truong VITE_CHAT_API_URL de noi backend.",
      role: "system" as const,
    };
  }

  const response = await fetch(apiUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ question }),
  });

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }

  const data = (await response.json().catch(() => null)) as
    | { answer?: string; message?: string }
    | null;

  return {
    text: data?.answer ?? data?.message ?? "Khong nhan duoc cau tra loi tu API.",
    role: "assistant" as const,
  };
}

export default function App() {
  const [currentConversation, setCurrentConversation] = useState<Conversation>(
    loadCurrentConversation,
  );
  const [savedConversations, setSavedConversations] = useState<Conversation[]>(
    loadSavedConversations,
  );
  const [selectedHistoryConversation, setSelectedHistoryConversation] =
    useState<Conversation | null>(null);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [isInfoOpen, setIsInfoOpen] = useState(false);
  const [isDonateView, setIsDonateView] = useState(false);
  const [isInfoView, setIsInfoView] = useState(false);
  const [historyVisibleCount, setHistoryVisibleCount] = useState(HISTORY_BATCH_SIZE);
  const [isDarkMode, setIsDarkMode] = useState(() => {
    const savedTheme = localStorage.getItem("theme");
    if (savedTheme === "dark") return true;
    if (savedTheme === "light") return false;
    return true;
  });

  useEffect(() => {
    document.documentElement.classList.toggle("theme-dark", isDarkMode);
    localStorage.setItem("theme", isDarkMode ? "dark" : "light");
  }, [isDarkMode]);

  useEffect(() => {
    localStorage.setItem(CURRENT_CONVERSATION_KEY, JSON.stringify(currentConversation));
  }, [currentConversation]);

  useEffect(() => {
    localStorage.setItem(SAVED_CONVERSATIONS_KEY, JSON.stringify(savedConversations));
    localStorage.removeItem(LEGACY_HISTORY_KEY);
  }, [savedConversations]);

  useEffect(() => {
    if (isHistoryOpen) {
      setHistoryVisibleCount(HISTORY_BATCH_SIZE);
    }
  }, [isHistoryOpen]);

  const messagesRef = useRef<HTMLDivElement | null>(null);

  useLayoutEffect(() => {
    const el = messagesRef.current;
    if (!el) {
      return;
    }

    el.scrollTop = el.scrollHeight;
  }, [currentConversation.messages]);

  const canSend = input.trim().length > 0 && !isSending;
  const visibleSavedConversations = useMemo(
    () => savedConversations.slice(0, historyVisibleCount),
    [historyVisibleCount, savedConversations],
  );

  function archiveCurrentConversation() {
    if (currentConversation.messages.length <= initialMessages.length) {
      return;
    }

    setSavedConversations((current) => {
      if (current.some((conversation) => conversation.id === currentConversation.id)) {
        return current;
      }

      const archivedConversation: Conversation = {
        ...currentConversation,
        title:
          currentConversation.title === DEFAULT_CONVERSATION_TITLE
            ? buildConversationTitle(currentConversation.messages)
            : currentConversation.title,
      };

      return [archivedConversation, ...current];
    });
  }

  function startNewChat() {
    archiveCurrentConversation();
    setCurrentConversation(createConversation());
    setInput("");
    setIsSending(false);
    setIsHistoryOpen(false);
    setSelectedHistoryConversation(null);
    setIsDonateView(false);
    setIsInfoView(false);
  }

  function openConversation(conversation: Conversation) {
    setSelectedHistoryConversation(conversation);
  }

  function clearHistory() {
    setSavedConversations([]);
    localStorage.removeItem(SAVED_CONVERSATIONS_KEY);
    setHistoryVisibleCount(HISTORY_BATCH_SIZE);
    setSelectedHistoryConversation(null);
  }

  function backToConversationList() {
    setSelectedHistoryConversation(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const question = input.trim();
    if (!question || isSending) {
      return;
    }

    const userMessage: Message = {
      id: Date.now(),
      role: "user",
      text: question,
    };

    setCurrentConversation((current) => {
      const messages = [...current.messages, userMessage];
      return {
        ...current,
        title:
          current.title === DEFAULT_CONVERSATION_TITLE
            ? buildConversationTitle(messages)
            : current.title,
        messages,
        updatedAt: Date.now(),
      };
    });
    setInput("");
    setIsSending(true);

    try {
      const reply = await sendQuestion(question);
      const replyMessage: Message = {
        id: Date.now() + 1,
        role: reply.role,
        text: reply.text,
      };

      setCurrentConversation((current) => ({
        ...current,
        messages: [...current.messages, replyMessage],
        updatedAt: Date.now(),
      }));
    } catch {
      const errorMessage: Message = {
        id: Date.now() + 1,
        role: "system",
        text: "Khong the gui cau hoi. Kiem tra lai API hoac ket noi mang.",
      };

      setCurrentConversation((current) => ({
        ...current,
        messages: [...current.messages, errorMessage],
        updatedAt: Date.now(),
      }));
    } finally {
      setIsSending(false);
    }
  }

    return (
      <main className="shell">
        <aside className="left-rail" aria-label="Thanh cong cu">
          <button
            type="button"
            className="rail-button rail-button--theme"
            onClick={() => setIsDarkMode((current) => !current)}
            aria-pressed={isDarkMode}
            aria-label="Bat hoac tat dark mode"
          >
            <span className="rail-button__label">{isDarkMode ? "Light" : "Dảk"}</span>
          </button>
          <button
            type="button"
            className="rail-button rail-button--home"
            onClick={() => {
              setIsDonateView(false);
              setIsInfoView(false);
            }}
            aria-label="Ve man hinh chinh"
            aria-pressed={!isDonateView && !isInfoView}
          >
            <span className="rail-button__label rail-button__label--home">⌂</span>
          </button>
          <div className="rail-bottom-actions">
            <button
              type="button"
              className="rail-button rail-button--star"
              onClick={() => {
                setIsDonateView(true);
                setIsInfoView(false);
              }}
              aria-pressed={isDonateView}
              aria-label="Mo cua so sao"
            >
              <span className="rail-button__label">✡</span>
            </button>
            <button
              type="button"
              className="rail-button rail-button--info"
              onClick={() => {
                setIsInfoView(true);
                setIsDonateView(false);
              }}
              aria-pressed={isInfoView}
              aria-label="Mo thong tin"
            >
              <span className="rail-button__label">ⓘ</span>
            </button>
          </div>
        </aside>

        <section className={`hero ${isDonateView || isInfoView ? "hero--donate" : ""}`}>
          {!isDonateView && !isInfoView ? (
            <div className="hero__copy">
              <p className="eyebrow">RAG Law VN</p>
              <h1>Giải đáp thắc mắc pháp luật cùng AI</h1>
              <p className="subtitle">Ửok In Process.</p>
            </div>
          ) : null}

          {isDonateView ? (
            <div className="donate-view">
              <div className="donate-panel">
                <div className="donate-panel__header">
                  
                  <h2>Khều Donate</h2>
                </div>
                <div className="donate-panel__content">
                  <img src={donateQr} alt="Donate QR" />
                  
                </div>
              </div>
            </div>
          ) : isInfoView ? (
            <div className="info-view">
              <div className="info-panel">
                <div className="donate-panel__header">
                  <h2 className="eyebrow">Thông tin</h2>
                  
                </div>
                <div className="info-panel__content">
                  <p>Dự án AI vớ vẩn</p>
                  
                </div>
              </div>
            </div>
          ) : (
            <div className="chat-stack">
              <div className="panel">
                <div
                  ref={messagesRef}
                  className="messages"
                  aria-live="polite"
                  aria-label="Lich su chat"
                >
                  {currentConversation.messages.map((message) => (
                    <article key={message.id} className={`bubble bubble--${message.role}`}>
                      {message.text}
                    </article>
                  ))}
                </div>

                <form className="composer" onSubmit={handleSubmit}>
                  <input
                    className="composer__input"
                    type="text"
                    value={input}
                    onChange={(event) => setInput(event.target.value)}
                    placeholder="Nhập câu hỏi cho AI..."
                    aria-label="Nhap cau hoi cho AI"
                  />
                  <button className="composer__button" type="submit" disabled={!canSend}>
                    {isSending ? "Đang gửi..." : "Gửi"}
                  </button>
                </form>
              </div>

              <div className="chat-actions">
                <button
                  type="button"
                  className="chat-action"
                  onClick={startNewChat}
                  aria-label="Tạo chat mới"
                >
                  Chat mới
                </button>
                <button
                  type="button"
                  className="chat-action"
                  onClick={() => setIsHistoryOpen((current) => !current)}
                  aria-expanded={isHistoryOpen}
                  aria-controls="chat-history-panel"
                  aria-label="Mở lịch sử chat"
                >
                  Lịch sử
                </button>
              </div>
            </div>
          )}
        </section>

      {isHistoryOpen ? (
        <div
          className="history-backdrop"
          role="presentation"
          onClick={() => setIsHistoryOpen(false)}
        >
          <aside
            id="chat-history-panel"
            className="history-panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="chat-history-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="history-panel__header">
              <div>
                <h2 id="chat-history-title">
                  {selectedHistoryConversation
                    ? selectedHistoryConversation.title
                    : "Lịch sử hội thoại"}
                </h2>
              </div>
              <div className="history-panel__actions">
                {selectedHistoryConversation ? (
                  <button
                    type="button"
                    className="history-panel__back"
                    onClick={backToConversationList}
                  >
                    Quay lai
                  </button>
                ) : (
                  <button
                    type="button"
                    className="history-panel__clear"
                    onClick={clearHistory}
                    disabled={savedConversations.length === 0}
                  >
                    Xóa lịch sử
                  </button>
                )}
                <button
                  type="button"
                  className="history-panel__close"
                  onClick={() => setIsHistoryOpen(false)}
                >
                  Đóng
                </button>
              </div>
            </div>

            <div className="history-panel__list" aria-label="Danh sach cuoc hoi thoai">
              {selectedHistoryConversation ? (
                <div className="history-detail">
                  <div className="history-detail__meta">
                    <span>{selectedHistoryConversation.messages.length} tin nhắn</span>
                    <span>{formatConversationTime(selectedHistoryConversation.updatedAt)}</span>
                  </div>
                  <div className="history-detail__messages" aria-label="Noi dung cuoc hoi thoai">
                    {selectedHistoryConversation.messages.map((message) => (
                      <article
                        key={`${selectedHistoryConversation.id}-${message.id}`}
                        className={`history-detail__message history-detail__message--${message.role}`}
                      >
                        <div className="history-detail__message-role">{message.role}</div>
                        <div className="history-detail__message-text">{message.text}</div>
                      </article>
                    ))}
                  </div>
                </div>
              ) : savedConversations.length === 0 ? (
                <p className="history-panel__empty">Chưa có cuộc hội thoại nào.</p>
              ) : (
                <>
                  {visibleSavedConversations.map((conversation) => (
                    <button
                      key={conversation.id}
                      type="button"
                      className="history-conversation"
                      onClick={() => openConversation(conversation)}
                    >
                      <div className="history-conversation__top">
                        <span className="history-conversation__title">{conversation.title}</span>
                        <span className="history-conversation__time">
                          {formatConversationTime(conversation.updatedAt)}
                        </span>
                      </div>
                      <div className="history-conversation__meta">
                        {conversation.messages.length} tin nhắn
                      </div>
                      <p className="history-conversation__preview">
                        {getConversationPreview(conversation)}
                      </p>
                    </button>
                  ))}
                  {visibleSavedConversations.length < savedConversations.length ? (
                    <button
                      type="button"
                      className="history-panel__more"
                      onClick={() =>
                        setHistoryVisibleCount((current) => current + HISTORY_BATCH_SIZE)
                      }
                    >
                      Tải thêm{" "}
                      {Math.min(
                        HISTORY_BATCH_SIZE,
                        savedConversations.length - visibleSavedConversations.length,
                      )}{" "}
                      cuộc hội thoại cũ hơn
                    </button>
                  ) : null}
                </>
              )}
            </div>
          </aside>
        </div>
      ) : null}

    </main>
  );
}
