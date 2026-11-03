import App from "@/App"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import "@/index.css"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { ThemeProvider } from "next-themes"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

const queryClient = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } } })

// Light only for now; the dark tokens stay in index.css for later.
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider attribute="class" forcedTheme="light">
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <App />
          <Toaster position="bottom-center" />
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)
