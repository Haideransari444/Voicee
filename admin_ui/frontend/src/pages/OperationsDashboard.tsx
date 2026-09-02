/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { CalendarClock, CheckCircle2, Phone, PhoneForwarded, ShieldOff, Target, Users } from 'lucide-react';
import { EmptyState, MetricCard, PageHeader, PageLoading, SectionCard, StatusBadge, secondaryButton } from '../components/operations/ProductUI';
import { Campaign, CampaignStats, CallStats, CallSummary, Lead, getCallStats, getCampaignLeads, getCampaignStats, getCampaigns, getRecentCalls, isAnswered, isQualified, sumValues } from '../services/operationsApi';

type CampaignView = { campaign: Campaign; stats: CampaignStats; leads: Lead[] };
const pct = (a: number, b: number) => b ? `${Math.round((a / b) * 100)}%` : '0%';
const formatDate = (value?: string | null) => value ? new Date(value).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '—';
const formatDuration = (seconds: number) => { const rounded = Math.max(0, Math.round(Number(seconds) || 0)); return `${Math.floor(rounded / 60)}m ${String(rounded % 60).padStart(2, '0')}s`; };

export default function OperationsDashboard() {
    const [campaigns, setCampaigns] = useState<CampaignView[]>([]);
    const [calls, setCalls] = useState<CallSummary[]>([]);
    const [callStats, setCallStats] = useState<CallStats | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => { (async () => {
        try {
            const all = await getCampaigns();
            const [views, recent, today] = await Promise.all([
                Promise.all(all.map(async campaign => ({ campaign, stats: await getCampaignStats(campaign.id), leads: await getCampaignLeads(campaign) }))),
                getRecentCalls(8),
                getCallStats({ start_date: new Date().toISOString().slice(0, 10) }),
            ]);
            setCampaigns(views); setCalls(recent); setCallStats(today);
        } catch (e: any) { setError(e?.response?.data?.detail || e?.message || 'Unable to load operations data.'); }
        finally { setLoading(false); }
    })(); }, []);

    const metrics = useMemo(() => {
        const leads = campaigns.flatMap(item => item.leads);
        const answered = leads.filter(isAnswered).length;
        const qualified = leads.filter(isQualified).length;
        const transfers = leads.filter(lead => Boolean(lead.last_transfer_successful)).length;
        const callbacks = leads.filter(lead => Boolean(lead.callback_at_utc)).length;
        const dnc = leads.filter(lead => Boolean(lead.do_not_call_at_utc)).length;
        const attempts = campaigns.reduce((n, item) => n + sumValues(item.stats.attempt_outcomes), 0);
        return { leads: leads.length, answered, qualified, transfers, callbacks, dnc, attempts };
    }, [campaigns]);

    if (loading) return <PageLoading label="Loading outbound operations" />;
    return <div className="space-y-8">
        <PageHeader eyebrow="Operations" title="Outbound performance" description="A live view of campaign progress, qualification, transfers, and follow-up activity." actions={<Link className={secondaryButton} to="/campaigns">View campaigns</Link>} />
        {error && <div role="alert" className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-700 dark:text-red-400">{error}</div>}
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-7">
            <MetricCard label="Calls today" value={callStats?.total_calls || 0} detail="Call history" icon={Phone} />
            <MetricCard label="Answered" value={metrics.answered} detail="Loaded campaign leads" icon={CheckCircle2} tone="success" />
            <MetricCard label="Qualified" value={metrics.qualified} detail="Deterministic result" icon={Target} tone="success" />
            <MetricCard label="Transferred" value={metrics.transfers} detail="Successful" icon={PhoneForwarded} tone="success" />
            <MetricCard label="Callbacks" value={metrics.callbacks} detail="Requested" icon={CalendarClock} tone="warning" />
            <MetricCard label="Do not call" value={metrics.dnc} detail="Suppressed" icon={ShieldOff} tone="danger" />
            <MetricCard label="Qualification rate" value={pct(metrics.qualified, metrics.answered)} detail="Of answered leads" icon={Users} />
        </div>

        <div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
            <SectionCard title="Qualification funnel" description="Current campaign totals">
                <div className="space-y-4 p-5">
                    {[['Leads', metrics.leads], ['Calls', metrics.attempts], ['Answered', metrics.answered], ['Qualified', metrics.qualified], ['Transferred', metrics.transfers]].map(([label, value], index) => <div key={String(label)}>
                        <div className="mb-1.5 flex justify-between text-sm"><span className="font-medium">{label}</span><span className="tabular-nums text-muted-foreground">{value}</span></div>
                        <div className="h-2 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary" style={{ width: `${metrics.leads ? Math.max(3, (Number(value) / metrics.leads) * 100) : 0}%`, opacity: 1 - index * 0.1 }} /></div>
                    </div>)}
                </div>
            </SectionCard>
            <SectionCard title="Campaign performance" description="Real campaign and lead state data">
                {!campaigns.length ? <EmptyState title="No campaigns yet" description="Create a campaign to begin tracking outbound performance." action={<Link to="/scheduling" className={secondaryButton}>Open campaign manager</Link>} /> : <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="bg-muted/50 text-xs text-muted-foreground"><tr>{['Campaign', 'Calls', 'Answer rate', 'Qualification', 'Transfers', 'Status'].map(h => <th key={h} className="px-5 py-3 font-medium">{h}</th>)}</tr></thead><tbody className="divide-y divide-border">{campaigns.map(({ campaign, stats, leads }) => {
                    const attempts = sumValues(stats.attempt_outcomes); const answered = leads.filter(isAnswered).length; const qualified = leads.filter(isQualified).length; const transfers = leads.filter(l => Boolean(l.last_transfer_successful)).length;
                    return <tr key={campaign.id} className="hover:bg-muted/30"><td className="px-5 py-4 font-medium">{campaign.name}</td><td className="px-5 py-4 tabular-nums">{attempts}</td><td className="px-5 py-4">{pct(answered, attempts)}</td><td className="px-5 py-4">{pct(qualified, answered)}</td><td className="px-5 py-4">{transfers}</td><td className="px-5 py-4"><StatusBadge value={campaign.status} /></td></tr>;
                })}</tbody></table></div>}
            </SectionCard>
        </div>

        <div className="grid gap-6 xl:grid-cols-[1.35fr_0.65fr]">
            <SectionCard title="Recent calls" action={<Link to="/calls" className="text-sm font-medium text-primary hover:underline">View all</Link>}>
                {!calls.length ? <EmptyState title="No calls recorded" description="Completed and active calls will appear here." /> : <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="bg-muted/50 text-xs text-muted-foreground"><tr>{['Lead', 'Agent', 'Duration', 'Outcome', 'Time'].map(h => <th key={h} className="px-5 py-3 font-medium">{h}</th>)}</tr></thead><tbody className="divide-y divide-border">{calls.map(call => <tr key={call.id}><td className="px-5 py-4"><p className="font-medium">{call.caller_name || call.caller_number || 'Unknown lead'}</p><p className="text-xs text-muted-foreground">{call.caller_number}</p></td><td className="px-5 py-4">{call.agent_name || call.context_name || '—'}</td><td className="px-5 py-4 tabular-nums">{formatDuration(call.duration_seconds)}</td><td className="px-5 py-4"><StatusBadge value={call.outcome} /></td><td className="px-5 py-4 text-muted-foreground">{formatDate(call.start_time)}</td></tr>)}</tbody></table></div>}
            </SectionCard>
            <SectionCard title="Upcoming callbacks">
                {campaigns.flatMap(x => x.leads).filter(l => l.callback_at_utc && new Date(l.callback_at_utc) >= new Date()).slice(0, 5).map(lead => <div key={lead.id} className="border-b border-border px-5 py-4 last:border-0"><p className="font-medium">{lead.name || lead.phone_number}</p><p className="mt-1 text-xs text-muted-foreground">{lead.campaign_name} · {formatDate(lead.callback_at_utc)}</p></div>)}
                {!campaigns.flatMap(x => x.leads).some(l => l.callback_at_utc && new Date(l.callback_at_utc) >= new Date()) && <EmptyState title="No upcoming callbacks" description="Callback requests will appear here when they are scheduled." />}
            </SectionCard>
        </div>
    </div>;
}
