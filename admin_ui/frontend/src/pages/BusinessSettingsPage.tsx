import { Link } from 'react-router-dom';
import { Cable, Phone, Settings } from 'lucide-react';
import { PageHeader, SectionCard, secondaryButton } from '../components/operations/ProductUI';

export default function BusinessSettingsPage({ section }: { section: 'general' | 'telephony' | 'integrations' }) {
    const meta = {
        general: { title: 'General settings', description: 'Business-level defaults for your outbound workspace.', icon: Settings },
        telephony: { title: 'Telephony settings', description: 'Business-facing calling and transfer configuration.', icon: Phone },
        integrations: { title: 'Integrations', description: 'Connected systems and platform services.', icon: Cable },
    }[section];
    const Icon = meta.icon;
    return <div className="space-y-8"><PageHeader eyebrow="Settings" title={meta.title} description={meta.description} />
        <SectionCard><div className="flex items-start gap-4 p-6"><div className="rounded-lg bg-primary/10 p-3 text-primary"><Icon className="h-5 w-5" /></div><div><h2 className="font-semibold">{section === 'general' ? 'Workspace configuration' : section === 'telephony' ? 'Campaign-level calling controls' : 'Infrastructure integrations'}</h2><p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">{section === 'general' ? 'The current backend does not expose a business workspace settings API. Product-wide values are therefore read-only in this view.' : section === 'telephony' ? 'Transfer destination and calling windows are stored per campaign and remain editable in the existing campaign manager. Raw PJSIP, codec, AudioSocket, and Asterisk configuration stays in Developer Tools.' : 'Provider and MCP configuration remain available to administrators in Developer Tools. No disconnected integration state is fabricated here.'}</p><div className="mt-5"><Link className={secondaryButton} to={section === 'telephony' ? '/scheduling' : section === 'integrations' ? '/providers' : '/developer/system-health'}>{section === 'telephony' ? 'Open campaign settings' : section === 'integrations' ? 'Open Developer Providers' : 'View system health'}</Link></div></div></div></SectionCard>
    </div>;
}
