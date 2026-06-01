import { FormEvent, useEffect, useState } from "react";

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
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isDarkMode, setIsDarkMode] = useState(() => {
    const savedTheme = localStorage.getItem("theme");
    if (savedTheme === "dark") return true;
    if (savedTheme === "light") return false;
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
  });

  useEffect(() => {
    document.documentElement.classList.toggle("theme-dark", isDarkMode);
    localStorage.setItem("theme", isDarkMode ? "dark" : "light");
  }, [isDarkMode]);

  const canSend = input.trim().length > 0 && !isSending;

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
    setInput("");
    setIsSending(true);

    try {
      const reply = await sendQuestion(question);
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          role: reply.role,
          text: reply.text,
        },
      ]);
    } catch {
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          role: "system",
          text: "Không thể gửi câu hỏi. Kiểm tra lại API hoặc kết nối mạng.",
        },
      ]);
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
        aria-label="Bật hoặc tắt dark mode"
      >
        {isDarkMode ? "Light mode" : "Dark mode"}
      </button>
      <section className="hero">
        <div className="hero__copy">
          <p className="eyebrow">RAG Law VN</p>
          <h1>Giải đáp thắc mắc pháp luật cùng AI</h1>
          <p className="subtitle">
            Ửok In Process.
          </p>
        </div>

        <div className="panel">
          <div className="messages" aria-live="polite" aria-label="Lịch sử chat">
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
      </section>
    </main>
  );
}
