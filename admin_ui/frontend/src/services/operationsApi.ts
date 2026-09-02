/* eslint-disable @typescript-eslint/no-explicit-any */
import axios from 'axios';

export type Campaign = {
    id: string;
    name: string;
    status: string;
    default_context: string;
    timezone?: string;
    daily_window_start_local?: string;
    daily_window_end_local?: string;
    qualification_rules?: Record<string, any>;
    human_transfer_destination?: string | null;
    system_prompt?: string | null;
    created_at_utc?: string;
    updated_at_utc?: string;
};

export type CampaignStats = {
    lead_states: Record<string, number>;
    attempt_outcomes: Record<string, number>;
};

export type Lead = {
    id: string;
    campaign_id: string;
    campaign_name?: string;
    name?: string | null;
    phone_number: string;
    state: string;
    attempt_count: number;
    custom_vars?: Record<string, any>;
    last_outcome?: string | null;
    last_attempt_at_utc?: string | null;
    last_started_at_utc?: string | null;
    last_duration_seconds?: number | null;
    last_context?: string | null;
    last_provider?: string | null;
    last_call_history_call_id?: string | null;
    last_summary?: string | null;
    last_transfer_attempted?: number | boolean | null;
    last_transfer_successful?: number | boolean | null;
    outcome_reason?: string | null;
    qualification_score?: number | null;
    qualification_state?: Record<string, any>;
    qualification_result?: Record<string, any>;
    do_not_call_at_utc?: string | null;
    callback_at_utc?: string | null;
};

export type CallSummary = {
    id: string;
    call_id: string;
    caller_number: string | null;
    caller_name: string | null;
    start_time: string | null;
    duration_seconds: number;
    provider_name: string;
    context_name: string | null;
    agent_name?: string | null;
    outcome: string;
    error_message?: string | null;
};

export type CallStats = {
    total_calls: number;
    avg_duration_seconds: number;
    outcomes: Record<string, number>;
    calls_per_day: Array<{ date: string; count: number }>;
    active_calls: number;
};

export type Agent = {
    slug: string;
    display_name: string;
    provider?: string;
    role_label?: string | null;
    voice?: string | null;
    is_active?: boolean | number;
};

export type KnowledgeDocument = {
    id: string;
    campaign_id?: string;
    name: string;
    content_type: string;
    character_count: number;
    chunk_count: number;
    created_at_utc: string;
};

export const getCampaigns = async () => {
    const response = await axios.get<Campaign[]>('/api/outbound/campaigns');
    return Array.isArray(response.data) ? response.data : [];
};

export const getCampaignStats = async (campaignId: string): Promise<CampaignStats> => {
    const response = await axios.get(`/api/outbound/campaigns/${campaignId}/stats`);
    return {
        lead_states: response.data?.lead_states || {},
        attempt_outcomes: response.data?.attempt_outcomes || {},
    };
};

export const getCampaignLeads = async (campaign: Campaign, pageSize = 200): Promise<Lead[]> => {
    const response = await axios.get(`/api/outbound/campaigns/${campaign.id}/leads`, {
        params: { page: 1, page_size: pageSize },
    });
    const rows = Array.isArray(response.data?.leads) ? response.data.leads : [];
    return rows.map((lead: Lead) => ({ ...lead, campaign_id: campaign.id, campaign_name: campaign.name }));
};

export const getRecentCalls = async (pageSize = 10): Promise<CallSummary[]> => {
    const response = await axios.get('/api/calls', { params: { page: 1, page_size: pageSize } });
    return Array.isArray(response.data?.calls) ? response.data.calls : [];
};

export const getCallStats = async (params?: Record<string, string>): Promise<CallStats> => {
    const response = await axios.get('/api/calls/stats', { params });
    return response.data;
};

export const getAgents = async (): Promise<Agent[]> => {
    const response = await axios.get('/api/agents');
    return Array.isArray(response.data) ? response.data : [];
};

export const getKnowledgeDocuments = async (campaignId: string): Promise<KnowledgeDocument[]> => {
    const response = await axios.get(`/api/outbound/campaigns/${campaignId}/knowledge`);
    return Array.isArray(response.data) ? response.data : [];
};

export const isQualified = (lead: Lead) => Boolean(lead.qualification_result?.qualified);
export const isAnswered = (lead: Lead) => {
    if (!lead.attempt_count) return false;
    const outcome = String(lead.last_outcome || '').toLowerCase();
    return !['no_answer', 'busy', 'machine_detected', 'failed', 'error'].includes(outcome);
};

export const sumValues = (values?: Record<string, number>) =>
    Object.values(values || {}).reduce((total, value) => total + Number(value || 0), 0);
