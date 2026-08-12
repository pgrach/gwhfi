"use client"

import { createContext, useContext, useEffect, useState } from "react"

type Theme = "light" | "dark"

interface ThemeContextType {
    theme: Theme
    toggleTheme: () => void
}

const ThemeContext = createContext<ThemeContextType>({
    theme: "dark",
    toggleTheme: () => { }
})

export function ThemeProvider({ children }: { children: React.ReactNode }) {
    const [theme, setTheme] = useState<Theme>("dark")
    const [mounted, setMounted] = useState(false)

    useEffect(() => {
        // Defer the browser-only preference lookup until after hydration. This
        // keeps the server and first client render identical without performing
        // a synchronous state update inside the effect itself.
        const frame = window.requestAnimationFrame(() => {
            let initialTheme: Theme = "dark"
            try {
                const stored = localStorage.getItem("smartwater-theme")
                initialTheme = stored === "light" || stored === "dark"
                    ? stored
                    : window.matchMedia("(prefers-color-scheme: dark)").matches
                        ? "dark"
                        : "light"
            } catch {
                // Keep the safe default when browser preference APIs are blocked.
            } finally {
                // Private browsing or hardened browser settings may make
                // localStorage throw. The dashboard must still finish mounting.
                setTheme(initialTheme)
                setMounted(true)
            }
        })

        return () => window.cancelAnimationFrame(frame)
    }, [])

    useEffect(() => {
        if (!mounted) return

        const root = document.documentElement
        if (theme === "dark") {
            root.classList.add("dark")
        } else {
            root.classList.remove("dark")
        }
        try {
            localStorage.setItem("smartwater-theme", theme)
        } catch {
            // The DOM theme remains usable even when persistence is unavailable.
        }
    }, [theme, mounted])

    const toggleTheme = () => {
        setTheme(prev => prev === "dark" ? "light" : "dark")
    }

    return (
        <ThemeContext.Provider value={{ theme, toggleTheme }}>
            {children}
        </ThemeContext.Provider>
    )
}

export function useTheme() {
    return useContext(ThemeContext)
}
