import { ChatPage } from "./pages/ChatPage"
import { LoginPage } from "./pages/LoginPage"
import { ManagePage } from "./pages/ManagePage"
import { SetupPage } from "./pages/SetupPage"
import { useAppLocation } from "./stores/history"

export function App() {
  const location = useAppLocation()
  switch (location.pathname) {
    case "/setup": return <SetupPage />
    case "/login": return <LoginPage />
    case "/manage": return <ManagePage />
    case "/chat": return <ChatPage />
    default: window.location.assign("/login"); return <main />
  }
}
