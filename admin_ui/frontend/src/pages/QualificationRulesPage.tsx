/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Check, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { EmptyState, PageHeader, PageLoading, SectionCard, inputClass, primaryButton, secondaryButton } from '../components/operations/ProductUI';
import { Campaign, getCampaigns } from '../services/operationsApi';

type Operator = 'equals' | 'gte' | 'gt' | 'lte' | 'lt' | 'eq';
type RuleRow = { id: string; field: string; operator: Operator; value: string; required: boolean };
const operatorLabels: Record<Operator, string> = { equals: 'equals', gte: 'greater than or equal', gt: 'greater than', lte: 'less than or equal', lt: 'less than', eq: 'numeric equals' };
const parse = (campaign?: Campaign): RuleRow[] => {
    const rules = campaign?.qualification_rules || {}; const rows: RuleRow[] = [];
    Object.entries(rules.required || {}).forEach(([field, value]) => rows.push({ id: crypto.randomUUID(), field, operator: 'equals', value: String(value), required: true }));
    Object.entries(rules.equals || {}).forEach(([field, value]) => rows.push({ id: crypto.randomUUID(), field, operator: 'equals', value: String(value), required: false }));
    Object.entries(rules.numeric || {}).forEach(([field, constraints]: [string, any]) => Object.entries(constraints || {}).forEach(([operator, value]) => rows.push({ id: crypto.randomUUID(), field, operator: operator as Operator, value: String(value), required: false })));
    return rows;
};
const value = (raw: string) => raw === 'true' ? true : raw === 'false' ? false : raw.trim() !== '' && Number.isFinite(Number(raw)) ? Number(raw) : raw;

export default function QualificationRulesPage() {
    const [campaigns, setCampaigns] = useState<Campaign[]>([]); const [campaignId, setCampaignId] = useState(''); const [rows, setRows] = useState<RuleRow[]>([]); const [loading, setLoading] = useState(true); const [saving, setSaving] = useState(false);
    useEffect(() => { getCampaigns().then(list => { setCampaigns(list); const first = list[0]; setCampaignId(first?.id || ''); setRows(parse(first)); }).finally(() => setLoading(false)); }, []);
    const select = (id: string) => { setCampaignId(id); setRows(parse(campaigns.find(c => c.id === id))); };
    const update = (id: string, patch: Partial<RuleRow>) => setRows(all => all.map(r => r.id === id ? { ...r, ...patch } : r));
    const payload = useMemo(() => { const out: any = { required: {}, equals: {}, numeric: {} }; rows.filter(r => r.field.trim()).forEach(r => { const v = value(r.value); if (r.required) out.required[r.field.trim()] = v; else if (r.operator === 'equals') out.equals[r.field.trim()] = v; else out.numeric[r.field.trim()] = { ...(out.numeric[r.field.trim()] || {}), [r.operator]: v }; }); if (!Object.keys(out.required).length) delete out.required; if (!Object.keys(out.equals).length) delete out.equals; if (!Object.keys(out.numeric).length) delete out.numeric; return out; }, [rows]);
    const save = async () => { setSaving(true); try { const { data } = await axios.patch(`/api/outbound/campaigns/${campaignId}`, { qualification_rules: payload }); setCampaigns(all => all.map(c => c.id === campaignId ? { ...c, ...data } : c)); toast.success('Qualification rules saved'); } catch (e: any) { toast.error(e?.response?.data?.detail || 'Could not save rules'); } finally { setSaving(false); } };
    if (loading) return <PageLoading label="Loading qualification rules" />;
    return <div className="space-y-8"><PageHeader eyebrow="AI workspace" title="Qualification Rules" description="Edit the deterministic campaign rules used after the agent collects structured lead information." actions={<button className={primaryButton} disabled={!campaignId || saving} onClick={save}><Check className="h-4 w-4" />{saving ? 'Saving…' : 'Save rules'}</button>} />
        <div className="max-w-sm"><label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-muted-foreground">Campaign</label><select className={inputClass} value={campaignId} onChange={e => select(e.target.value)}><option value="">Select campaign</option>{campaigns.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
        <SectionCard title="Rule configuration" description="Only operators supported by the existing deterministic engine are available." action={<button className={secondaryButton} disabled={!campaignId} onClick={() => setRows(all => [...all, { id: crypto.randomUUID(), field: '', operator: 'equals', value: 'true', required: false }])}><Plus className="h-4 w-4" /> Add rule</button>}>
            {!campaignId ? <EmptyState title="Select a campaign" description="Rules are stored directly on campaigns; no separate rule-set entity is invented." /> : !rows.length ? <EmptyState title="No rules configured" description="Add a deterministic rule to define qualification." /> : <div className="divide-y divide-border">{rows.map(row => <div key={row.id} className="grid items-end gap-3 p-5 md:grid-cols-[1.1fr_1.25fr_0.8fr_auto_auto]"><label className="text-xs font-medium text-muted-foreground">Field<input className={`${inputClass} mt-2`} value={row.field} onChange={e => update(row.id, { field: e.target.value })} placeholder="decision_maker" /></label><label className="text-xs font-medium text-muted-foreground">Operator<select className={`${inputClass} mt-2`} value={row.operator} onChange={e => update(row.id, { operator: e.target.value as Operator })}>{Object.entries(operatorLabels).map(([op, label]) => <option key={op} value={op}>{label}</option>)}</select></label><label className="text-xs font-medium text-muted-foreground">Value<input className={`${inputClass} mt-2`} value={row.value} onChange={e => update(row.id, { value: e.target.value })} /></label><label className="flex h-9 items-center gap-2 text-sm"><input type="checkbox" checked={row.required} onChange={e => update(row.id, { required: e.target.checked, operator: e.target.checked ? 'equals' : row.operator })} /> Required</label><button onClick={() => setRows(all => all.filter(r => r.id !== row.id))} className="grid h-9 w-9 place-items-center rounded-md text-muted-foreground hover:bg-red-500/10 hover:text-red-600"><Trash2 className="h-4 w-4" /></button></div>)}</div>}
        </SectionCard>
        <SectionCard title="Human-readable preview"><div className="space-y-3 p-5">{!rows.length && <p className="text-sm text-muted-foreground">No qualification conditions configured.</p>}{rows.filter(r => r.field).map(r => <p key={r.id} className="flex items-center gap-3 text-sm"><span className="grid h-5 w-5 place-items-center rounded-full bg-emerald-500/10 text-emerald-700"><Check className="h-3 w-3" /></span><span><span className="font-medium capitalize">{r.field.replace(/_/g, ' ')}</span> {operatorLabels[r.operator]} <span className="font-semibold">{r.value}</span>{r.required && <span className="ml-2 text-xs text-muted-foreground">required</span>}</span></p>)}</div></SectionCard>
    </div>;
}
