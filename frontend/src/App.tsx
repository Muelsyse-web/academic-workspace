import { useEffect, useState, lazy, Suspense } from "react";
import { HashRouter, NavLink, Route, Routes, Link } from "react-router-dom";
import {
  BookOpen,
  LayoutDashboard,
  LibraryBig,
  Search,
  Sun,
  Moon,
  PanelLeftClose,
  GraduationCap,
  ShieldCheck,
  NotebookPen,
  Layers,
  MessageSquare,
  Settings as SettingsIcon,
} from "lucide-react";
const Learning = lazy(() =>
  import("./pages/Learning").then((m) => ({ default: m.Learning })),
);
const Chat = lazy(() =>
  import("./pages/Chat").then((m) => ({ default: m.Chat })),
);
const Settings = lazy(() =>
  import("./pages/Settings").then((m) => ({ default: m.Settings })),
);
const Notes = lazy(() =>
  import("./pages/Notes").then((m) => ({ default: m.Notes })),
);
import { Dashboard } from "./pages/Dashboard";
import { Courses } from "./pages/Courses";
import { Library } from "./pages/Library";
import { Search as SearchPage } from "./pages/Search";
import { DocumentView } from "./pages/DocumentView";
import "./styles.css";
export default function App() {
  const [theme, setTheme] = useState(
      () => localStorage.getItem("scholar-theme") || "system",
    ),
    [menu, setMenu] = useState(false);
  useEffect(() => {
    const media = matchMedia("(prefers-color-scheme: dark)");
    function apply() {
      document.documentElement.dataset.theme =
        theme === "system" ? (media.matches ? "dark" : "light") : theme;
    }
    apply();
    localStorage.setItem("scholar-theme", theme);
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme]);
  return (
    <HashRouter>
      <div className="app-shell">
        <aside className={"sidebar " + (menu ? "mobile-open" : "")}>
          <Link className="brand" to="/" onClick={() => setMenu(false)}>
            <span className="brand-mark">
              <GraduationCap size={25} />
            </span>
            <div>
              Scholar<span>LOCAL ACADEMIC WORKSPACE</span>
            </div>
          </Link>
          <div className="workspace-label">
            <span className="avatar">S</span>
            <div>
              我的学术空间<small>Personal workspace</small>
            </div>
            <span className="live-dot" />
          </div>
          <span className="nav-label">学习空间</span>
          <nav aria-label="主导航">
            {[
              [LayoutDashboard, "/", "学习概览"],
              [BookOpen, "/courses", "我的课程"],
              [LibraryBig, "/library", "资料库"],
              [Search, "/search", "知识搜索"],
              [NotebookPen, "/notes", "学习笔记"],
              [MessageSquare, "/chat", "AI 学术问答"],
              [Layers, "/learning", "练习与复习"],
              [SettingsIcon, "/settings", "设置"],
            ].map(([Icon, to, label]) => {
              const Glyph = Icon as typeof BookOpen;
              return (
                <NavLink
                  key={String(to)}
                  to={String(to)}
                  end={to === "/"}
                  onClick={() => setMenu(false)}
                >
                  <Glyph size={19} />
                  {String(label)}
                </NavLink>
              );
            })}
          </nav>
          <div className="sidebar-bottom">
            <div className="device-card">
              <ShieldCheck size={19} />
              <div>
                本地优先<small>资料保存在你的设备</small>
              </div>
            </div>
            <label className="theme-select">
              <Sun size={16} />
              <select
                aria-label="外观主题"
                value={theme}
                onChange={(e) => setTheme(e.target.value)}
              >
                <option value="system">跟随系统</option>
                <option value="light">浅色模式</option>
                <option value="dark">深色模式</option>
              </select>
              <Moon size={15} />
            </label>
          </div>
        </aside>
        {menu && (
          <button
            className="menu-scrim"
            aria-label="关闭导航"
            onClick={() => setMenu(false)}
          />
        )}
        <div className="main-shell">
          <div className="topbar">
            <button
              className="icon-button mobile-menu"
              aria-label="打开导航"
              onClick={() => setMenu((v) => !v)}
            >
              <PanelLeftClose size={21} />
            </button>
            <span>
              学术空间 <span className="breadcrumb">/</span> 学习与探索
            </span>
            <div>
              <span className="local-indicator">
                <span className="live-dot" /> 本地工作空间
              </span>
              <span className="avatar small">S</span>
            </div>
          </div>
          <main>
            <Suspense
              fallback={<div className="loading">正在打开学习空间…</div>}
            >
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/courses" element={<Courses />} />
                <Route path="/library" element={<Library />} />
                <Route path="/search" element={<SearchPage />} />
                <Route path="/notes" element={<Notes />} />
                <Route path="/chat" element={<Chat />} />
                <Route path="/learning" element={<Learning />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="/documents/:id" element={<DocumentView />} />
                <Route
                  path="*"
                  element={
                    <div>
                      <h1>页面不存在</h1>
                      <Link to="/">返回概览</Link>
                    </div>
                  }
                />
              </Routes>
            </Suspense>
          </main>
          <footer>
            Scholar <span>为专注的学习，留一处安静的空间。</span>
          </footer>
        </div>
      </div>
    </HashRouter>
  );
}
