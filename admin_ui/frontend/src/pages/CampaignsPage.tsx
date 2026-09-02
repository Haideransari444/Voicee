/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus } from 'lucide-react';
import { EmptyState, PageHeader, PageLoading, SectionCard, StatusBadge, primaryButton } from '../components/operations/ProductUI';
import { Campaign, CampaignStats, Lead, getCampaignLeads, getCampaignStats, getCampaigns, isAnswered, isQualified, sumValues } from '../services/operationsApi';

type Row = { campaign: Campaign; stats: CampaignStats; leads: Lead[] };
const pct = (a: number, b: number) => b ? `${Math.round(a / b * 100)}%` : '0%';

export default function CampaignsPage() {
    const [rows, setRows] = useState<Row[]>([]); const [loading, setLoading] = useState(true); const [error, setError] = useState('');
    useEffect(() => { (async () => { try { const campaigns = await getCampaigns(); setRows(await Promise.all(campaigns.map(async campaign => ({ campaign, stats: await getCampaignStats(campaign.id), leads: await getCampaignLeads(campaign) })))); } catch (e: any) { setError(e?.message || 'Unable to load campaigns.'); } finally { setLoading(false); } })(); }, []);
    if (loading) return <PageLoading label="Loading campaigns" />;
    return <div className="space-y-8"><PageHeader eyebrow="Outbound" title="Campaigns" description="Track campaign execution, qualification performance, transfers, and follow-up." actions={<Link to="/scheduling" className={primaryButton}><Plus className="h-4 w-4" /> New campaign</Link>} />
        {error && <div className="rounded-lg border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-700">{error}</div>}
        <SectionCard>{!rows.length ? <EmptyState title="No campaigns" description="Create your first outbound campaign to add leads, knowledge, and qualification rules." action={<Link to="/scheduling" className={primaryButton}>Create campaign</Link>} /> : <div className="overflow-x-auto"><table className="w-full min-w-[980px] text-left text-sm"><thead className="bg-muted/50 text-xs text-muted-foreground"><tr>{['Campaign', 'Agent', 'Leads', 'Calls', 'Answered', 'Qualified', 'Transferred', 'Qual. rate', 'Status'].map(h => <th className="px-5 py-3 font-medium" key={h}>{h}</th>)}</tr></thead><tbody className="divide-y divide-border">{rows.map(({ campaign, stats, leads }) => { const answered = leads.filter(isAnswered).length; const qualified = leads.filter(isQualified).length; const transferred = leads.filter(l => Boolean(l.last_transfer_successful)).length; return <tr key={campaign.id} className="hover:bg-muted/30"><td className="px-5 py-4"><p className="font-semibold">{campaign.name}</p><Link to="/scheduling" className="text-xs text-primary hover:underline">Manage campaign</Link></td><td className="px-5 py-4">{campaign.default_context || '—'}</td><td className="px-5 py-4 tabular-nums">{leads.length}</td><td className="px-5 py-4 tabular-nums">{sumValues(stats.attempt_outcomes)}</td><td className="px-5 py-4 tabular-nums">{answered}</td><td className="px-5 py-4 tabular-nums">{qualified}</td><td className="px-5 py-4 tabular-nums">{transferred}</td><td className="px-5 py-4 font-medium">{pct(qualified, answered)}</td><td className="px-5 py-4"><StatusBadge value={campaign.status} /></td></tr>; })}</tbody></table></div>}</SectionCard>
    </div>;
}
