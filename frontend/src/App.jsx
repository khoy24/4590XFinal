import { useState, useRef, useEffect } from "react";

function App() {
  // functions TBD

  // State Management
  const [awsStatus, setAwsStatus] = useState("disconnected");
  const [messages, setMessages] = useState([
    {
      role: "bot",
      text: "Hello! I am your Cloud Security Architect. Please connect your AWS account to get started.",
    },
  ]);
  const [inputText, setInputText] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  // Auto-scroll logic for the chat window
  const messagesEndRef = useRef(null);
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Handle AWS Connection
  const handleConnectAWS = () => {
    if (awsStatus === "connected" || awsStatus === "pending") return;
    setAwsStatus("pending");
    setTimeout(() => {
      setAwsStatus("connected");
      setMessages((prev) => [
        ...prev,
        {
          role: "system",
          text: "AWS Account Successfully Linked! You can now ask me to deploy infrastructure.",
        },
      ]);
    }, 2000);
  };

  // Handle Chat Submission
  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!inputText.trim() || awsStatus !== "connected") return;

    const userMessage = { role: "user", text: inputText };
    setMessages((prev) => [...prev, userMessage]);
    setInputText("");
    setIsLoading(true);

    try {
      const response = await fetch("http://localhost:8000/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: userMessage.text }),
      });

      if (!response.ok) throw new Error("Backend connection failed");

      const data = await response.json();
      setMessages((prev) => [...prev, { role: "bot", text: data.reply }]);
    } catch (error) {
      console.error(error);
      setMessages((prev) => [
        ...prev,
        {
          role: "bot",
          text: "System Error: Could not reach the backend.",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    // main layout
    <div className="flex h-screen w-screen bg-white font-mono overflow-hidden">
      {/* leftside panel */}
      <aside className="w-[55%] h-full flex flex-col justify-start items-center text-center pt-[5vh] px-[5vw]">
        {/* Title and Subtitle Grouped */}
        <div className="mb-4">
          <h1 className="text-4xl md:text-5xl font-normal text-black tracking-tight">
            Cloud Deployment Assistant
          </h1>
          <p className="text-sm text-gray-500 mt-2 tracking-widest uppercase">
            Powered by Gemini
          </p>
        </div>

        {/* Button to connect to AWS */}
        <button
          onClick={handleConnectAWS}
          className={`px-10 py-2 font-medium text-xl rounded-full transition-all duration-200 shadow-sm ${
            awsStatus === "connected"
              ? "bg-green-100 text-green-800"
              : awsStatus === "pending"
                ? "bg-yellow-100 text-yellow-800 cursor-wait"
                : "bg-[#C1C4FF] text-black hover:bg-[#b8b7e8]"
          }`}
        >
          {awsStatus === "connected"
            ? "AWS Connected"
            : awsStatus === "pending"
              ? "Connecting..."
              : "Connect to AWS"}
        </button>
      </aside>

      {/* chat panel */}
      <section className="w-[45%] h-full py-[5vh] pr-[4vw] pl-[1vw]">
        {/* gray chat frame */}
        <div className="w-full h-full bg-[#F0F0F0] flex flex-col relative rounded-sm">
          {/* chat messages area */}
          <main className="flex-1 overflow-y-auto p-6 scrollbar-thin">
            <div className="flex flex-col space-y-4">
              {messages.map((msg, index) => (
                <div
                  key={index}
                  className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[85%] px-5 py-3 rounded-2xl text-sm leading-relaxed ${
                      msg.role === "user"
                        ? "bg-white text-black rounded-br-none shadow-sm"
                        : msg.role === "system"
                          ? "bg-gray-200 text-gray-700 w-full text-center rounded-xl font-bold text-xs uppercase tracking-wider"
                          : "bg-white text-black rounded-bl-none shadow-sm"
                    }`}
                  >
                    {msg.text}
                  </div>
                </div>
              ))}
              {isLoading && (
                <div className="flex justify-start">
                  <div className="bg-white px-5 py-3 rounded-2xl rounded-bl-none text-gray-500 italic shadow-sm text-sm">
                    Processing request...
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          </main>

          {/* expandable input area */}
          <footer className="p-4 w-full">
            <form
              onSubmit={handleSendMessage}
              className="flex items-end bg-white rounded-2xl overflow-hidden shadow-sm"
            >
              <textarea
                value={inputText}
                onChange={(e) => {
                  setInputText(e.target.value);
                  // Auto-resize logic:
                  e.target.style.height = "auto";
                  e.target.style.height = e.target.scrollHeight + "px";
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSendMessage(e);
                  }
                }}
                placeholder="user will type in their question/request here"
                disabled={awsStatus !== "connected"}
                className="flex-1 px-5 py-4 bg-transparent text-black text-sm focus:outline-none resize-none overflow-y-auto min-h-[52px] max-h-[150px] disabled:opacity-50"
                rows="1"
              />

              {/* Send Button matching my Figma Icon */}
              <div className="p-2 flex-shrink-0">
                <button
                  type="submit"
                  disabled={
                    !inputText.trim() || awsStatus !== "connected" || isLoading
                  }
                  className="p-2 bg-[#C1C4FF] rounded-xl text-black hover:bg-[#b8b7e8] transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="20"
                    height="20"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <line x1="7" y1="17" x2="17" y2="7"></line>
                    <polyline points="7 7 17 7 17 17"></polyline>
                  </svg>
                </button>
              </div>
            </form>
          </footer>
        </div>
      </section>
    </div>
  );
}

export default App;
