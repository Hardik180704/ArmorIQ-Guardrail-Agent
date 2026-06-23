import axios from "axios"

const API = axios.create({
    baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
})

// ---- AGENT ----
export const sendMessage = async (message: string, conversationId?: string) => {
    const res = await API.post("/chat", { message, conversation_id: conversationId })
    return res.data
}

// ---- RULES ----
export const getRules = async () => {
    const res = await API.get("/rules")
    return res.data.rules
}

export const addRule = async (rule: any) => {
    const res = await API.post("/rules", rule)
    return res.data
}

export const deleteRule = async (ruleId: string) => {
    const res = await API.delete(`/rules/${ruleId}`)
    return res.data
}

export const toggleRule = async (ruleId: string, enabled: boolean) => {
    const res = await API.patch(`/rules/${ruleId}/toggle?enabled=${enabled}`)
    return res.data
}

// ---- LOGS ----
export const getLogs = async () => {
    const res = await API.get("/logs")
    return res.data.logs
}