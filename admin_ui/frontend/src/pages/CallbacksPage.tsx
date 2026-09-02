import { useEffect, useMemo, useState } from 'react';
import { Phone, Search } from 'lucide-react';
import { EmptyState, PageHeader, PageLoading, SectionCard, StatusBadge, inputClass } from '../components/operations/ProductUI';
import { Lead, getCampaignLeads, getCampaigns } from '../services/operationsApi';

const formatDate = (value?: string | null) => value
    ? new Date(value).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
    : '—';

export default function CallbacksPage() {
    const [leads, setLeads] = useState<Lead[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [query, setQuery] = useState('');
    const [filter, setFilter] = useState<'upcoming' | 'all'>('upcoming');

    useEffect(() => {
        (async () => {
            try {
                const campaigns = await getCampaigns();
                setLeads((await Promise.all(campaigns.map(campaign => getCampaignLeads(campaign)))).flat());
            } catch (e: unknown) {
                setError(e instanceof Error ? e.message : 'Unable to load callbacks.');
            } finally {
                setLoading(false);
            }
        })();
    }, []);

    const callbacks = useMemo(() => {
        const now = Date.now();
        return leads
            .filter(lead => lead.callback_at_utc)
            .filter(lead => filter === 'all' || new Date(lead.callback_at_utc as string).getTime() >= now)
            .filter(lead => [lead.name, lead.phone_number, lead.campaign_name].some(value => String(value || '').toLowerCase().includes(query.toLowerCase())))
            .sort((a, b) => new Date(a.callback_at_utc as string).getTime() - new Date(b.callback_at_utc as string).getTime());
    }, [leads, filter, query]);

    if (loading) return <PageLoading label="Loading callbacks" />;
    return <div className="space-y-8">
        <PageHeader eyebrow="Outbound" title="Callbacks" description="Keep follow-up attempts visible and actionable for the sales team." />
        {error && <div role="alert" className="rounded-lg border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-700 dark:text-red-400">{error}</div>}
        <SectionCard action={<div className="flex flex-wrap items-center gap-2">
            <div className="relative w-56"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" /><input className={`${inputClass} pl-9`} placeholder="Search callbacks…" value={query} onChange={event => setQuery(event.target.value)} /></div>
            <div className="flex rounded-md border border-border bg-muted/40 p-1" role="group" aria-label="Callback filter">
                {(['upcoming', 'all'] as const).map(value => <button key={value} type="button" onClick={() => setFilter(value)} className={`rounded px-3 py-1.5 text-xs font-medium capitalize ${filter === value ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>{value}</button>)}
            </div>
            </div>}>
            {!callbacks.length ? <EmptyState title={filter === 'upcoming' ? 'No upcoming callbacks' : 'No callbacks recorded'} description="Callback requests from qualified conversations will appear here." /> : <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-left text-sm"><thead className="bg-muted/50 text-xs text-muted-foreground"><tr>{['Lead', 'Campaign', 'Scheduled for', 'Last outcome', 'Phone', 'Status'].map(header => <th key={header} className="px-5 py-3 font-medium">{header}</th>)}</tr></thead><tbody className="divide-y divide-border">{callbacks.map(lead => { const upcoming = new Date(lead.callback_at_utc as string).getTime() >= Date.now(); return <tr key={lead.id} className="hover:bg-muted/30"><td className="px-5 py-4"><p className="font-medium">{lead.name || 'Unnamed lead'}</p><p className="text-xs text-muted-foreground">{lead.custom_vars?.company || '—'}</p></td><td className="px-5 py-4">{lead.campaign_name || '—'}</td><td className="px-5 py-4 font-medium">{formatDate(lead.callback_at_utc)}</td><td className="px-5 py-4">{lead.last_outcome ? <StatusBadge value={lead.last_outcome} /> : '—'}</td><td className="px-5 py-4 tabular-nums">{lead.phone_number}</td><td className="px-5 py-4"><StatusBadge value={upcoming ? 'scheduled' : 'completed'} /></td></tr>; })}</tbody></table></div>}
        </SectionCard>
        <div className="flex items-center gap-2 text-xs text-muted-foreground"><Phone className="h-3.5 w-3.5" /> Callback timing comes from the existing campaign lead records.</div>
    </div>;
}
