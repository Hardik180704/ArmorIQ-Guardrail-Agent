"use client"
import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { sendMessage, getRules, addRule, deleteRule, toggleRule, getLogs } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { Shield, MessageSquare, ScrollText, Trash2, Plus } from "lucide-react"

// ---- TYPES ----
interface Message {
    role: "user" | "agent"
    content: string
    blocked?: boolean
}

interface Rule {
    id: string
    type: string
    tool: string
    enabled: boolean
    reason?: string
    max_tokens?: number
}

interface Log {
    conversation_id: string
    user_message: string
    agent_response: string
    blocked: boolean
}

export default function Dashboard() {
    const queryClient = useQueryClient()

    // Chat state
    const [messages, setMessages] = useState<Message[]>([])
    const [input, setInput] = useState("")
    const [conversationId, setConversationId] = useState<string>()

    // New rule form state
    const [newRule, setNewRule] = useState({
        type: "block",
        tool: "",
        reason: "",
        enabled: true,
    })

    // ---- QUERIES ----
    const { data: rules = [] } = useQuery({
        queryKey: ["rules"],
        queryFn: getRules,
    })

    const { data: logs = [] } = useQuery({
        queryKey: ["logs"],
        queryFn: getLogs,
    })

    // ---- MUTATIONS ----
    const chatMutation = useMutation({
        mutationFn: ({ message, convId }: { message: string; convId?: string }) =>
            sendMessage(message, convId),
        onSuccess: (data) => {
            setConversationId(data.conversation_id)
            setMessages(prev => [...prev, {
                role: "agent",
                content: data.response,
                blocked: data.blocked
            }])
            queryClient.invalidateQueries({ queryKey: ["logs"] })
        }
    })

    const addRuleMutation = useMutation({
        mutationFn: addRule,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["rules"] })
            setNewRule({ type: "block", tool: "", reason: "", enabled: true })
        }
    })

    const deleteRuleMutation = useMutation({
        mutationFn: deleteRule,
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ["rules"] })
    })

    const toggleMutation = useMutation({
        mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
            toggleRule(id, enabled),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ["rules"] })
    })

    // ---- HANDLERS ----
    const handleSend = () => {
        if (!input.trim()) return
        setMessages(prev => [...prev, { role: "user", content: input }])
        chatMutation.mutate({ message: input, convId: conversationId })
        setInput("")
    }

    const handleAddRule = () => {
        if (!newRule.tool) return
        addRuleMutation.mutate(newRule)
    }

    // ---- RULE BADGE COLORS ----
    const ruleColor = (type: string) => {
        switch (type) {
            case "block": return "destructive"
            case "require_approval": return "warning"
            case "input_validation": return "secondary"
            case "budget": return "outline"
            default: return "default"
        }
    }

    return (
        <div className="h-screen bg-[#0B0B0C] text-zinc-100 p-6 flex flex-col overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between mb-6 shrink-0 border-b border-zinc-800 pb-4">
                <div className="flex items-center gap-3">
                    {/* SVG logo inspired by the website wave circle */}
                    <svg className="w-7 h-7 text-[#e05a2b] shrink-0" viewBox="0 0 100 100" fill="none">
                        <circle cx="50" cy="50" r="42" stroke="#e05a2b" strokeWidth="8" />
                        <path d="M30 52 C 38 35, 44 35, 50 50 C 56 65, 62 65, 70 46" stroke="#e05a2b" strokeWidth="8" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                    <div>
                        <h1 className="text-lg font-black tracking-wider text-white">ARMORIQ</h1>
                        <p className="text-zinc-500 text-[10px] font-mono tracking-widest uppercase">INTENT ASSURANCE GATEWAY</p>
                    </div>
                </div>

                {/* Top right status inspired by the website stats header */}
                <div className="flex items-center gap-4 text-[10px] font-mono tracking-wider">
                    <div className="flex items-center gap-2 text-zinc-500">
                        <span className="relative flex h-2 w-2">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#e05a2b] opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-[#e05a2b]"></span>
                        </span>
                        <span>// POLICY ENGINE ACTIVE</span>
                    </div>
                    <div className="h-4 w-px bg-zinc-800" />
                    <div className="text-[#e05a2b] flex items-center gap-2">
                        <span>■ // ACTIONS VERIFIED</span>
                        <span className="font-bold font-sans text-xs bg-[#e05a2b]/10 px-2 py-0.5 border border-[#e05a2b]/20 text-[#e05a2b]">{logs.length}</span>
                    </div>
                </div>
            </div>

            <div className="flex-1 flex flex-col gap-6 min-h-0">
                <div className="grid grid-cols-2 gap-6 min-h-0 flex-1">
                    {/* ---- CHAT PANEL ---- */}
                    <div className="bg-[#121214] border border-[#242427] rounded-none flex flex-col min-h-0">
                        <div className="shrink-0 px-4 py-3.5 border-b border-zinc-850 flex items-center justify-between">
                            <h2 className="text-xs font-mono tracking-wider text-zinc-400 uppercase flex items-center gap-2">
                                <span className="text-[#e05a2b]">01 //</span> AGENT INTERACTION
                            </h2>
                            <MessageSquare className="w-4 h-4 text-zinc-600" />
                        </div>
                        
                        <div className="flex-1 flex flex-col min-h-0 p-4">
                            {/* Messages */}
                            <div className="flex-1 overflow-y-auto mb-4 space-y-3 pr-2 min-h-0">
                                {messages.length === 0 && (
                                    <div className="text-zinc-650 text-center mt-24 space-y-2">
                                        <p className="font-mono font-bold text-zinc-500">// NO ACTIVE SESSION</p>
                                        <p className="text-[11px] font-sans text-zinc-600">Send a message to initialize the guardrail session...</p>
                                    </div>
                                )}
                                {messages.map((msg, i) => (
                                    <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                                        <div className={`max-w-[85%] border px-4 py-2.5 text-xs rounded-none ${
                                            msg.role === "user"
                                                ? "bg-[#e05a2b]/10 border-[#e05a2b]/30 text-zinc-200 font-sans"
                                                : msg.blocked
                                                    ? "bg-red-950/20 border-red-900/60 text-red-200 font-mono"
                                                    : "bg-[#18181b] border-zinc-800 text-zinc-300 font-sans"
                                        }`}>
                                            {msg.role === "user" && <div className="text-[9px] text-[#e05a2b] font-mono mb-1 font-bold uppercase tracking-wider">// USER_QUERY</div>}
                                            {msg.role === "agent" && !msg.blocked && <div className="text-[9px] text-zinc-500 font-mono mb-1 font-bold uppercase tracking-wider">// AGENT_RESPONSE</div>}
                                            {msg.blocked && <div className="text-[9px] text-red-400 mb-1 font-bold font-mono tracking-wider">🚫 INTENT_BLOCKED: POLICY_VIOLATION</div>}
                                            <div className="whitespace-pre-wrap leading-relaxed">{msg.content}</div>
                                        </div>
                                    </div>
                                ))}
                                {chatMutation.isPending && (
                                    <div className="flex justify-start">
                                        <div className="bg-[#18181b] border border-zinc-800 text-zinc-500 px-4 py-2.5 text-xs font-mono">
                                            <span className="inline-block animate-pulse">// AGENT THINKING... SECURING TRANSIT</span>
                                        </div>
                                    </div>
                                )}
                            </div>

                            {/* Input */}
                            <div className="flex gap-2 shrink-0">
                                <Input
                                    value={input}
                                    onChange={e => setInput(e.target.value)}
                                    onKeyDown={e => e.key === "Enter" && handleSend()}
                                    placeholder="Ask the agent something..."
                                    className="bg-zinc-900/50 border-zinc-800 text-zinc-100 rounded-none focus:border-[#e05a2b] focus-visible:ring-0 focus-visible:ring-offset-0 text-xs font-mono h-9 flex-1"
                                />
                                <Button
                                    onClick={handleSend}
                                    disabled={chatMutation.isPending}
                                    className="bg-[#e05a2b] hover:bg-[#c94f24] text-white rounded-none text-xs font-mono h-9 px-6 shrink-0"
                                >
                                    SEND
                                </Button>
                            </div>
                        </div>
                    </div>

                    {/* ---- RULES PANEL ---- */}
                    <div className="bg-[#121214] border border-[#242427] rounded-none flex flex-col min-h-0">
                        <div className="shrink-0 px-4 py-3.5 border-b border-zinc-850 flex items-center justify-between">
                            <h2 className="text-xs font-mono tracking-wider text-zinc-400 uppercase flex items-center gap-2">
                                <span className="text-[#e05a2b]">02 //</span> SECURE POLICY RULES
                            </h2>
                            <Shield className="w-4 h-4 text-zinc-600" />
                        </div>
                        
                        <div className="flex-1 flex flex-col min-h-0 p-4">
                            {/* Existing Rules */}
                            <div className="flex-1 overflow-y-auto mb-4 space-y-2 pr-2 min-h-0">
                                {rules.length === 0 && (
                                    <p className="text-zinc-600 text-xs font-mono text-center mt-10">
                                        // NO ACTIVE POLICIES LOADED
                                    </p>
                                )}
                                {rules.map((rule: Rule) => (
                                    <div key={rule.id} className={`flex items-center justify-between bg-[#18181b] border-y border-zinc-800/30 px-3 py-2 transition-colors ${rule.enabled ? 'border-l-2 border-l-[#e05a2b]' : 'border-l-2 border-l-zinc-700'}`}>
                                        <div className="flex items-center gap-2 min-w-0">
                                            <span className={`font-mono text-[9px] px-1.5 py-0.5 border ${
                                                rule.type === 'block' ? 'border-red-950 text-red-400 bg-red-950/10' : 'border-zinc-800 text-zinc-400'
                                            } rounded-none`}>{rule.type.toUpperCase()}</span>
                                            <span className="text-xs font-mono font-bold text-zinc-300 truncate">{rule.tool}</span>
                                        </div>
                                        <div className="flex items-center gap-3">
                                            <Switch checked={rule.enabled} onCheckedChange={(checked) => toggleMutation.mutate({ id: rule.id, enabled: checked })} className="data-[state=checked]:bg-[#e05a2b] data-[state=unchecked]:bg-zinc-800" />
                                            <Button variant="ghost" size="sm" onClick={() => deleteRuleMutation.mutate(rule.id)} className="text-zinc-500 hover:text-red-400 hover:bg-zinc-800 rounded-none h-7 w-7 p-0">
                                                <Trash2 className="w-3.5 h-3.5" />
                                            </Button>
                                        </div>
                                    </div>
                                ))}
                            </div>

                            {/* Add New Rule */}
                            <div className="border-t border-zinc-800 pt-3 space-y-2 shrink-0">
                                <p className="text-[9px] text-[#e05a2b] font-mono font-semibold uppercase tracking-wider">// DEFINE NEW POLICY RULE</p>
                                <div className="flex gap-2">
                                    <select
                                        value={newRule.type}
                                        onChange={e => setNewRule(p => ({ ...p, type: e.target.value }))}
                                        className="bg-zinc-900 border border-zinc-800 rounded-none px-3 h-9 text-xs text-zinc-300 font-mono focus:border-[#e05a2b] focus:ring-0 outline-none w-1/3"
                                    >
                                        <option value="block">Block</option>
                                        <option value="require_approval">Require Approval</option>
                                        <option value="input_validation">Input Validation</option>
                                        <option value="budget">Budget</option>
                                    </select>
                                    <Input
                                        value={newRule.tool}
                                        onChange={e => setNewRule(p => ({ ...p, tool: e.target.value }))}
                                        placeholder="tool (e.g. delete_record)"
                                        className="bg-zinc-900/50 border-zinc-800 text-zinc-100 rounded-none text-xs font-mono focus:border-[#e05a2b] focus-visible:ring-0 focus-visible:ring-offset-0 h-9 flex-1"
                                    />
                                </div>
                                <div className="flex gap-2">
                                    <Input
                                        value={newRule.reason}
                                        onChange={e => setNewRule(p => ({ ...p, reason: e.target.value }))}
                                        placeholder="policy justification (optional)"
                                        className="bg-zinc-900/50 border-zinc-800 text-zinc-100 rounded-none text-xs font-mono focus:border-[#e05a2b] focus-visible:ring-0 focus-visible:ring-offset-0 h-9 flex-1"
                                    />
                                    <Button
                                        onClick={handleAddRule}
                                        disabled={addRuleMutation.isPending}
                                        className="bg-[#e05a2b] hover:bg-[#c94f24] text-white rounded-none shrink-0 h-9 px-4"
                                    >
                                        <Plus className="w-4 h-4" />
                                    </Button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* ---- LOGS PANEL ---- */}
                <div className="bg-[#121214] border border-[#242427] rounded-none flex flex-col min-h-0 flex-[0.7]">
                    <div className="shrink-0 px-4 py-3.5 border-b border-zinc-850 flex items-center justify-between">
                        <h2 className="text-xs font-mono tracking-wider text-zinc-400 uppercase flex items-center gap-2">
                            <span className="text-[#e05a2b]">03 //</span> LIVE INTENT AUDIT LOGS
                        </h2>
                        <div className="flex items-center gap-3">
                            <span className="border border-zinc-800 px-2 py-0.5 text-[9px] text-zinc-500 font-mono">
                                POLLING: 3000MS
                            </span>
                            <ScrollText className="w-4 h-4 text-zinc-600" />
                        </div>
                    </div>
                    
                    <div className="flex-1 overflow-y-auto p-4 min-h-0">
                        <div className="space-y-2">
                            {logs.length === 0 && (
                                <p className="text-zinc-650 text-xs font-mono text-center py-8">
                                    // NO OPERATIONS REGISTERED YET
                                </p>
                            )}
                            {logs.map((log: Log, i: number) => (
                                <div key={i} className={`flex items-start gap-3 border-b border-zinc-900/50 px-3 py-2 text-xs font-mono rounded-none ${
                                    log.blocked ? "bg-red-950/10 border-l-2 border-l-red-600" : "border-l-2 border-l-green-600 bg-zinc-900/30"
                                }`}>
                                    <span className="shrink-0 text-xs mt-0.5">{log.blocked ? "❌" : "🛡️"}</span>
                                    <div className="min-w-0 flex-1 space-y-1">
                                        <div className="flex items-center gap-2 text-[10px]">
                                            <span className="text-zinc-500">CONV_ID:</span>
                                            <span className="text-zinc-400 truncate max-w-[120px]">{log.conversation_id}</span>
                                            <div className="ml-auto">
                                                <span className={`text-[9px] uppercase px-1.5 py-0.2 border rounded-none font-bold ${
                                                    log.blocked ? 'border-red-900/40 text-red-400' : 'border-green-900/40 text-green-400'
                                                }`}>
                                                    {log.blocked ? 'BLOCKED' : 'VERIFIED'}
                                                </span>
                                            </div>
                                        </div>
                                        <p className="text-zinc-300 text-xs font-sans">
                                            <span className="text-zinc-500 font-mono text-[9px] mr-1.5">USER:</span>
                                            {log.user_message}
                                        </p>
                                        <p className="text-zinc-400 text-xs font-sans">
                                            <span className="text-zinc-500 font-mono text-[9px] mr-1.5">AGENT:</span>
                                            {log.agent_response}
                                        </p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}