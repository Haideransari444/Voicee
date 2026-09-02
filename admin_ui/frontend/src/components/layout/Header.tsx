import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ChevronRight, CheckCircle, Moon, Sun, Monitor, Search } from 'lucide-react';
import { useTheme } from '../../hooks/useTheme';
import { PRODUCT } from '../../config/product';

const labels: Record<string, string> = { analytics: 'Analytics', campaigns: 'Campaigns', leads: 'Leads', calls: 'Calls', scheduling: 'Campaign Manager', callbacks: 'Callbacks', agents: 'Agents', 'knowledge-base': 'Knowledge Base', 'qualification-rules': 'Qualification Rules', settings: 'Settings', general: 'General', telephony: 'Telephony', integrations: 'Integrations', developer: 'Developer Tools', 'system-health': 'System Health', providers: 'Providers', pipelines: 'Pipelines', profiles: 'Audio Profiles', tools: 'Tools', mcp: 'MCP', vad: 'Voice Detection', streaming: 'Streaming', llm: 'LLM Defaults', transport: 'Audio Transport', 'barge-in': 'Barge-in', yaml: 'Advanced Configuration', env: 'Environment', docker: 'Docker Services', asterisk: 'Asterisk', logs: 'Logs', terminal: 'Terminal', models: 'Models' };
const Header = () => {
    const { pathname } = useLocation();
    const { theme, cycleTheme } = useTheme();
    const segments = pathname.split('/').filter(Boolean);
    return <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-border bg-background px-6 lg:px-8">
        <div className="flex min-w-0 items-center gap-2 text-sm text-muted-foreground"><Link to="/" className="font-medium hover:text-foreground">{PRODUCT.name}</Link>{segments.map((segment, index) => <React.Fragment key={`${segment}-${index}`}><ChevronRight className="h-3.5 w-3.5" /><span className={index === segments.length - 1 ? 'truncate font-medium text-foreground' : ''}>{labels[segment] || segment.replace(/-/g, ' ')}</span></React.Fragment>)}</div>
        <div className="flex items-center gap-2"><button title="Open command palette (Ctrl+K)" className="hidden h-9 items-center gap-2 rounded-md border border-border bg-card px-3 text-xs text-muted-foreground hover:bg-accent md:flex"><Search className="h-3.5 w-3.5" /> Search <kbd className="rounded border border-border bg-muted px-1.5 py-0.5">Ctrl K</kbd></button><Link to="/developer/system-health" className="hidden items-center gap-1.5 rounded-md px-2 py-1.5 text-xs text-muted-foreground hover:bg-accent sm:flex"><CheckCircle className="h-3.5 w-3.5 text-emerald-600" /> System operational</Link><button onClick={cycleTheme} title={`Theme: ${theme}`} className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground">{theme === 'light' ? <Sun className="h-4 w-4" /> : theme === 'dark' ? <Moon className="h-4 w-4" /> : <Monitor className="h-4 w-4" />}</button></div>
    </header>;
};
export default Header;
