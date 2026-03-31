"use client";

import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Shield, Send, RefreshCw, ChevronRight, Globe, Lock } from "lucide-react";

// --- Types ---
interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: any[];
  rawContext?: any;
}

interface NewsItem {
  id: string;
  document: string;
  metadata: any;
}

export default function VigilancePortal() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [feed, setFeed] = useState<NewsItem[]>([]);
  const [isIntroActive, setIsIntroActive] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  // --- Fetch Feed on Load ---
  useEffect(() => {
    fetchFeed();
  }, []);

  const fetchFeed = async () => {
    try {
      const res = await fetch("http://localhost:8000/feed");
      const data = await res.json();
      if (!data.error) setFeed(data);
    } catch (e) {
      console.error("Feed link broken:", e);
    }
  };

  const handleSync = async () => {
    await fetch("http://localhost:8000/sync", { method: "POST" });
    fetchFeed();
  };

  // --- Streaming Chat Logic ---
  const handleSendMessage = async () => {
    if (!input.trim() || isStreaming) return;
    
    const userMsg: Message = { role: "user", content: input };
    const tempInput = input;
    setInput("");
    setIsStreaming(true);
    
    // Add User Message and an empty Assistant Message placeholder
    setMessages((prev) => [...prev, userMsg, { role: "assistant", content: "" }]);

    try {
      const response = await fetch("http://localhost:8000/chat", {
        method: "POST",
        body: JSON.stringify({ query: tempInput }),
        headers: { "Content-Type": "application/json" },
      });

      if (!response.ok) throw new Error("Server disconnected");
      if (!response.body) return;

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = ""; // Buffer for partial JSON lines
      
      let currentAssistantContent = "";
      let currentSources: any[] = [];

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        
        // Save the last partial line back to the buffer
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const payload = JSON.parse(line);
            if (payload.type === "sources") {
              currentSources = payload.data;
            } else if (payload.type === "content") {
              currentAssistantContent += payload.data;
            }

            // Batch update the UI with current state
            setMessages((prev) => {
              const newMsgs = [...prev];
              newMsgs[newMsgs.length - 1] = { 
                role: "assistant", 
                content: currentAssistantContent, 
                sources: currentSources 
              };
              return newMsgs;
            });
          } catch (e) {
            console.error("Partial JSON error, skipping line:", line);
          }
        }
      }
    } catch (e) {
      console.error("Fatal Stream Error:", e);
      setMessages((prev) => {
        const newMsgs = [...prev];
        newMsgs[newMsgs.length - 1] = { 
          role: "assistant", 
          content: "⚠️ System Link Interrupted. Please check if your FastAPI backend is still running." 
        };
        return newMsgs;
      });
    } finally {
      setIsStreaming(false);
    }
  };

  // --- Utility: Language Check ---
  const isUrdu = (text: string) => /[\u0600-\u06FF]/.test(text);

  return (
    <main className="h-screen flex flex-col bg-[#020617] text-slate-100 selection:bg-blue-500/30 overflow-hidden">
      
      {/* --- ELITE INTRO OVERLAY --- */}
      <AnimatePresence>
        {isIntroActive && (
          <motion.div 
            initial={{ opacity: 1 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.8 }}
            className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-[#020617]"
          >
            <motion.div 
              animate={{ scale: [1, 1.1, 1], opacity: [0.5, 1, 0.5] }}
              transition={{ repeat: Infinity, duration: 3 }}
              className="w-24 h-24 rounded-full bg-blue-600/20 flex items-center justify-center mb-8 border border-blue-500/30"
            >
              <Shield className="w-12 h-12 text-blue-500" />
            </motion.div>
            <motion.h1 
              initial={{ y: 20, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              className="text-4xl font-light tracking-[0.2em] mb-4 text-white"
            >
              VIGILANCE-PK
            </motion.h1>
            <motion.p 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.5 }}
              className="text-slate-500 text-sm tracking-widest uppercase mb-12"
            >
              Advanced Intelligence Hub
            </motion.p>
            <button 
              onClick={() => setIsIntroActive(false)}
              className="px-8 py-3 bg-blue-600 hover:bg-blue-500 transition-all rounded-lg font-semibold tracking-tighter text-sm flex items-center gap-2 group"
            >
              INITIALIZE COMMAND CENTER <ChevronRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* --- MAIN HEADER --- */}
      <header className="h-20 glass sticky top-0 z-40 flex items-center justify-between px-8 border-b border-white/5">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 rounded-lg bg-blue-600/10 flex items-center justify-center border border-blue-500/20">
            <Shield className="w-5 h-5 text-blue-500" />
          </div>
          <h2 className="text-xl font-bold tracking-tight">Vigilance-PK <span className="text-blue-500 text-sm font-normal">PRO</span></h2>
        </div>
        <div className="flex items-center gap-6">
          <button onClick={handleSync} className="flex items-center gap-2 text-xs text-slate-400 hover:text-white transition-colors">
            <RefreshCw className="w-3 h-3" /> SYNC PIPELINE
          </button>
          <div className="flex items-center gap-2 px-3 py-1 bg-green-500/10 rounded-full border border-green-500/20">
            <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
            <span className="text-[10px] font-bold text-green-500 uppercase tracking-widest">System Live</span>
          </div>
        </div>
      </header>

      {/* --- DASHBOARD LAYOUT --- */}
      <div className="flex-1 flex overflow-hidden h-[calc(100vh-80px)]">
        
        {/* --- LEFT SIDEBAR (INTEL FEED) --- */}
        <aside className="w-[380px] border-r border-white/5 flex flex-col bg-slate-900/20 shrink-0">
          <div className="p-6 border-b border-white/5">
            <div className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1 flex items-center gap-2">
              <Globe className="w-3 h-3" /> Latest Human Rights Intel
            </div>
            <p className="text-xs text-slate-400">Ground truth logs from local news extraction</p>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-3 custom-scrollbar">
            {feed.map((item, i) => (
              <motion.div 
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 }}
                key={item.id} 
                className="glass rounded-xl p-4 hover:border-white/20 transition-all group cursor-pointer"
              >
                <div className="text-[10px] text-blue-400 mb-2 flex justify-between">
                  <span>{item.metadata.source}</span>
                  <span>{item.metadata.published?.slice(0, 10)}</span>
                </div>
                <h3 className={`text-sm font-semibold mb-2 leading-snug ${isUrdu(item.document) ? 'urdu text-right' : ''}`}>
                  {item.document.split("\n")[0]}
                </h3>
                <div className="flex flex-wrap gap-1 mt-2">
                  {item.metadata.major_categories && item.metadata.major_categories.split(",").filter((t: string) => t.trim()).map((tag: string) => (
                    <span key={tag} className="text-[9px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded border border-white/5 uppercase font-bold">{tag}</span>
                  ))}
                </div>
              </motion.div>
            ))}
          </div>
        </aside>

        {/* --- MAIN CHAT INTERFACE --- */}
        <section className="flex-1 flex flex-col relative">
          
          {/* BACKGROUND DECORATION */}
          <div className="absolute inset-0 overflow-hidden pointer-events-none opacity-20">
             <div className="absolute top-[20%] left-[30%] w-[400px] h-[400px] bg-blue-600/30 rounded-full blur-[120px]" />
          </div>

          <div className="flex-1 overflow-y-auto p-8 space-y-8 scroll-smooth" ref={scrollRef}>
            {messages.length === 0 && (
              <div className="h-full flex flex-col items-center justify-center text-center opacity-40">
                <Shield className="w-16 h-16 text-blue-500 mb-6" />
                <h3 className="text-2xl font-light tracking-widest mb-2 uppercase">Command Engine Ready</h3>
                <p className="text-sm max-w-md">Query the localized database to analyze human rights trends, violation reports, and policy changes across Pakistan.</p>
              </div>
            )}
            
            {messages.map((msg, i) => (
              <motion.div 
                key={i}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div className={`max-w-[70%] rounded-2xl p-6 ${
                  msg.role === "user" 
                    ? "bg-blue-600 text-white" 
                    : "glass border-l-4 border-l-blue-500"
                }`}>
                  <p className={`text-[15px] leading-relaxed whitespace-pre-wrap ${isUrdu(msg.content) ? 'urdu text-right' : ''}`}>
                    {msg.content}
                  </p>
                  
                  {msg.sources && (
                    <div className="mt-6 pt-4 border-t border-white/10">
                      <div className="text-[10px] font-bold text-slate-500 mb-3 flex items-center gap-2">
                        <Lock className="w-3 h-3" /> VERIFIED RELEVANT SOURCES
                      </div>
                      <div className="grid grid-cols-1 gap-2">
                        {msg.sources.map((src, idx) => (
                          <a 
                            key={idx} 
                            href={src.link} 
                            target="_blank" 
                            className="text-[11px] text-blue-400 hover:text-blue-300 transition-colors flex items-center gap-1 group"
                          >
                            <ChevronRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
                            {src.source}: {src.title}
                          </a>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </motion.div>
            ))}
          </div>

          {/* CHAT INPUT */}
          <div className="p-8">
            <div className="max-w-4xl mx-auto flex gap-4">
              <div className="flex-1 relative">
                 <input 
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSendMessage()}
                  placeholder="Initiate analysis query..."
                  className="w-full h-14 bg-white/5 border border-white/10 rounded-xl px-6 focus:outline-none focus:border-blue-500 transition-all text-sm tracking-tight"
                />
              </div>
              <button 
                onClick={handleSendMessage}
                disabled={isStreaming}
                className="w-14 h-14 rounded-xl bg-blue-600 flex items-center justify-center hover:bg-blue-500 transition-all disabled:opacity-50"
              >
                <Send className="w-5 h-5" />
              </button>
            </div>
            <div className="text-center mt-4 opacity-30 text-[10px] tracking-[0.2em] uppercase">
              Vigilance-PK RAG ENGINE v2.0 // OFFLINE INTEL
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
