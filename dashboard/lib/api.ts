import axios from "axios"

const API = axios.create({
    baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
})

interface RulePayload {
    type: string
    tool: string
    enabled: boolean
    reason?: string
}

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

export const addRule = async (rule: RulePayload) => {
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

// ---- APPROVALS ----
export const getApprovals = async (status?: string) => {
    const res = await API.get("/approvals", { params: status ? { status } : undefined })
    return res.data.approvals
}

export const approveApproval = async (approvalId: string) => {
    const res = await API.post(`/approvals/${approvalId}/approve`, { reason: "Approved from dashboard" })
    return res.data
}

export const rejectApproval = async (approvalId: string) => {
    const res = await API.post(`/approvals/${approvalId}/reject`, { reason: "Rejected from dashboard" })
    return res.data
}

// ---- LOGS ----
export const getLogs = async () => {
    const res = await API.get("/logs")
    return res.data.logs
}
