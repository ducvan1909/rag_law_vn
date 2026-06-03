import { FormEvent, useEffect, useLayoutEffect, useRef, useState } from "react";

type MessageRole = "assistant" | "system" | "user";

type Message = {
  id: number;
  role: MessageRole;
  text: string;
};

const initialMessages: Message[] = [
  {
    id: 1,
    role: "assistant",
    text: "Hỏi nhanh con mẹ mày lên",
  },
];

const CHAT_HISTORY_KEY = "rag-law-vn.chat-history";
const HISTORY_BATCH_SIZE = 100;

function loadSavedHistory() {
  const savedMessages = localStorage.getItem(CHAT_HISTORY_KEY);
  if (!savedMessages) {
    return [] as Message[];
  }

  try {
    const parsed = JSON.parse(savedMessages) as Message[];
    if (!Array.isArray(parsed)) {
      return [];
    }

    return parsed.filter(
      (message) =>
        message &&
        typeof message.id === "number" &&
        (message.role === "assistant" ||
          message.role === "system" ||
          message.role === "user") &&
        typeof message.text === "string",
    );
  } catch {
    return [];
  }
}

function formatMessageTime(id: number) {
  if (id < 1_000_000_000_000) {
    return "";
  }

  return new Date(id).toLocaleString("vi-VN");
}

async function sendQuestion(question: string) {
  const apiUrl = import.meta.env.VITE_CHAT_API_URL;

  if (!apiUrl) {
    return {
      text: "Chưa cấu hình API. Hãy đặt biến môi trường VITE_CHAT_API_URL để nối backend.",
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
    text:
      data?.answer ??
      data?.message ??
      "Không nhận được câu trả lời từ API.",
    role: "assistant" as const,
  };
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [historyMessages, setHistoryMessages] = useState<Message[]>(loadSavedHistory);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
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
    localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(historyMessages));
  }, [historyMessages]);

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
  }, [messages]);

  const canSend = input.trim().length > 0 && !isSending;
  const visibleHistoryMessages = historyMessages.slice(
    Math.max(historyMessages.length - historyVisibleCount, 0),
  );

  function clearHistory() {
    setHistoryMessages([]);
    localStorage.removeItem(CHAT_HISTORY_KEY);
    setHistoryVisibleCount(HISTORY_BATCH_SIZE);
  }

  function startNewChat() {
    setMessages(initialMessages);
    setInput("");
    setIsSending(false);
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

    setMessages((current) => [...current, userMessage]);
    setHistoryMessages((current) => [...current, userMessage]);
    setInput("");
    setIsSending(true);

    try {
      const reply = await sendQuestion(question);
      const replyMessage: Message = {
        id: Date.now() + 1,
        role: reply.role,
        text: reply.text,
      };

      setMessages((current) => [...current, replyMessage]);
      setHistoryMessages((current) => [...current, replyMessage]);
    } catch {
      const errorMessage: Message = {
        id: Date.now() + 1,
        role: "system",
        text: "Không thể gửi câu hỏi. Kiểm tra lại API hoặc kết nối mạng.",
      };

      setMessages((current) => [...current, errorMessage]);
      setHistoryMessages((current) => [...current, errorMessage]);
    } finally {
      setIsSending(false);
    }
  }

  return (
    <main className="shell">
      <button
        type="button"
        className="theme-toggle"
        onClick={() => setIsDarkMode((current) => !current)}
        aria-pressed={isDarkMode}
        aria-label="Bật hoặc tắt dảk mode"
      >
        {isDarkMode ? "Light mode" : "Dảk mode"}
          </button>
      <section className="hero">
        <div className="hero__copy">
          <p className="eyebrow">RAG Law VN</p>
          <h1>Giải đáp thắc mắc pháp luật cùng AI</h1>
          <p className="subtitle">Ửok in process.</p>
        </div>

        <div className="chat-stack">
          <div className="panel">
            <div
              ref={messagesRef}
              className="messages"
              aria-live="polite"
              aria-label="Lịch sử chat"
            >
              {messages.map((message) => (
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
                aria-label="Nhập câu hỏi cho AI"
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
                <h2 id="chat-history-title">Lịch sử chat</h2>
              </div>
              <div className="history-panel__actions">
                <button
                  type="button"
                  className="history-panel__clear"
                  onClick={clearHistory}
                  disabled={historyMessages.length === 0}
                >
                  Xóa lịch sử
                </button>
                <button
                  type="button"
                  className="history-panel__close"
                  onClick={() => setIsHistoryOpen(false)}
                >
                  Đóng
                </button>
              </div>
            </div>

            <div className="history-panel__list" aria-label="Danh sách lịch sử chat">
              {historyMessages.length === 0 ? (
                   <p className="history-panel__empty">Chưa có lịch sử chat nào.</p>
              ) : (
                <>
                  {visibleHistoryMessages.map((message) => (
                    <article
                      key={`${message.role}-${message.id}`}
                      className={`history-item history-item--${message.role}`}
                    >
                      <div className="history-item__meta">
                        <span className="history-item__role">{message.role}</span>
                        <span className="history-item__time">{formatMessageTime(message.id)}</span>
                      </div>
                      <p className="history-item__text">{message.text}</p>
                    </article>
                  ))}
                  {visibleHistoryMessages.length < historyMessages.length ? (
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
                        historyMessages.length - visibleHistoryMessages.length,
                      )}{" "}
                      tin nhắn cũ hơn
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
