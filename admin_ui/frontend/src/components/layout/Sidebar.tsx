import React, { useState } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import {
    Activity, BarChart3, BookOpen, Bot, Brain, CalendarClock, ChevronLeft,
    ChevronRight, CircleUserRound, Code2, Container, FileText, Gauge,
    HardDrive, LayoutDashboard, ListChecks, LogOut, Lock, Phone, Plug,
    Radio, Server, Settings, Sliders, Terminal, Users, Wrench, Workflow, Zap,
} from 'lucide-react';
import { useAuth } from '../../auth/AuthContext';
import { useSidebarCollapsed } from '../../hooks/useSidebarCollapsed';
import { PRODUCT, type ProductMode } from '../../config/product';
import ChangePasswordModal from '../auth/ChangePasswordModal';

type Item = { to: string; icon: React.ElementType; label: string; end?: boolean };
type Group = { title: string; items: Item[] };

const operationsGroups: Group[] = [
    { title: 'Overview', items: [
        { to: '/', icon: LayoutDashboard, label: 'Dashboard', end: true },
        { to: '/analytics', icon: BarChart3, label: 'Analytics' },
    ] },
    { title: 'Outbound', items: [
        { to: '/campaigns', icon: Gauge, label: 'Campaigns' },
        { to: '/leads', icon: Users, label: 'Leads' },
        { to: '/calls', icon: Phone, label: 'Calls' },
        { to: '/callbacks', icon: CalendarClock, label: 'Callbacks' },
    ] },
    { title: 'AI', items: [
        { to: '/agents', icon: Bot, label: 'Agents' },
        { to: '/knowledge-base', icon: BookOpen, label: 'Knowledge Base' },
        { to: '/qualification-rules', icon: ListChecks, label: 'Qualification Rules' },
    ] },
    { title: 'Settings', items: [
        { to: '/settings/general', icon: Settings, label: 'General' },
        { to: '/settings/integrations', icon: Plug, label: 'Integrations' },
    ] },
];

const developerGroups: Group[] = [
    { title: 'System', items: [
        { to: '/developer/system-health', icon: Activity, label: 'System Health' },
        { to: '/docker', icon: Container, label: 'Docker Services' },
        { to: '/asterisk', icon: Phone, label: 'Asterisk' },
        { to: '/logs', icon: FileText, label: 'Logs' },
        { to: '/terminal', icon: Terminal, label: 'Terminal' },
    ] },
    { title: 'AI infrastructure', items: [
        { to: '/providers', icon: Server, label: 'Providers' },
        { to: '/pipelines', icon: Workflow, label: 'Pipelines' },
        { to: '/models', icon: HardDrive, label: 'Models' },
    ] },
    { title: 'Audio', items: [
        { to: '/profiles', icon: Sliders, label: 'Audio Profiles' },
        { to: '/vad', icon: Activity, label: 'Voice Detection' },
        { to: '/streaming', icon: Zap, label: 'Streaming' },
        { to: '/transport', icon: Radio, label: 'Audio Transport' },
        { to: '/barge-in', icon: Radio, label: 'Barge-in' },
    ] },
    { title: 'Tooling', items: [
        { to: '/tools', icon: Wrench, label: 'Tools' },
        { to: '/mcp', icon: Plug, label: 'MCP' },
    ] },
    { title: 'Configuration', items: [
        { to: '/llm', icon: Brain, label: 'LLM Defaults' },
        { to: '/yaml', icon: Code2, label: 'Advanced Configuration' },
    ] },
];

const Sidebar = () => {
    const { user, logout } = useAuth();
    const { collapsed, toggle } = useSidebarCollapsed();
    const location = useLocation();
    const navigate = useNavigate();
    const routeIsDeveloper = ['/developer/', '/providers', '/pipelines', '/profiles', '/tools', '/mcp', '/vad', '/streaming', '/llm', '/transport', '/barge-in', '/yaml', '/env', '/docker', '/asterisk', '/logs', '/terminal', '/models', '/updates', '/wizard'].some(prefix => location.pathname.startsWith(prefix));
    const [mode, setMode] = useState<ProductMode>(() => routeIsDeveloper ? 'developer' : (localStorage.getItem('callflow-mode') as ProductMode) || 'operations');
    const [passwordOpen, setPasswordOpen] = useState(false);
    const groups = mode === 'operations' ? operationsGroups : developerGroups;

    const switchMode = (next: ProductMode) => {
        localStorage.setItem('callflow-mode', next);
        setMode(next);
        navigate(next === 'developer' ? '/developer/system-health' : '/');
    };

    return (
        <aside className={`${collapsed ? 'w-[72px]' : 'w-[264px]'} flex h-full shrink-0 flex-col border-r border-border bg-card transition-[width] duration-200`}>
            <div className={`flex h-[72px] items-center border-b border-border ${collapsed ? 'justify-center px-2' : 'gap-3 px-5'}`}>
                <div className="min-w-0 shrink-0"><img src={collapsed ? '/callflow-mark.png' : '/callflow-logo.png'} alt={collapsed ? PRODUCT.name : `${PRODUCT.name} logo`} className={`${collapsed ? 'h-7 w-7' : 'h-8 w-[142px]'} object-contain object-left brightness-0 invert`} /></div>
                <button onClick={toggle} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} aria-expanded={!collapsed} className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground">
                    {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
                </button>
            </div>
            <div className={`mx-3 mt-4 grid rounded-lg bg-muted p-1 ${collapsed ? 'grid-cols-1' : 'grid-cols-2'}`}>
                {(['operations', 'developer'] as ProductMode[]).map(value => <button key={value} title={value} onClick={() => switchMode(value)} className={`rounded-md px-2 py-1.5 text-xs font-semibold capitalize transition-colors ${mode === value ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>{collapsed ? (value === 'operations' ? 'OP' : 'DEV') : value}</button>)}
            </div>
            <nav aria-label="Main navigation" data-mode={mode} className="flex-1 overflow-y-auto px-3 py-5">
                {groups.map(group => <div key={group.title} className="mb-6">
                    {!collapsed && <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{group.title}</p>}
                    <div className="space-y-1">{group.items.map(({ to, icon: Icon, label, end }) => <NavLink key={to} to={to} end={end} title={collapsed ? label : undefined} className={({ isActive }) => `flex h-10 items-center rounded-md px-3 text-sm font-medium transition-colors ${collapsed ? 'justify-center' : 'gap-3'} ${isActive ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-accent hover:text-foreground'}`}><Icon className="h-[18px] w-[18px] shrink-0" />{!collapsed && <span>{label}</span>}</NavLink>)}</div>
                </div>)}
            </nav>
            <div className="border-t border-border p-3">
                <div className={`mb-2 flex items-center ${collapsed ? 'justify-center' : 'gap-3 px-2'} py-2`}><div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-muted"><CircleUserRound className="h-4 w-4" /></div>{!collapsed && <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{user?.username || 'Admin'}</p><p className="text-xs text-muted-foreground">Administrator</p></div>}</div>
                <div className={`flex ${collapsed ? 'flex-col' : ''} gap-1`}><button onClick={() => setPasswordOpen(true)} title="Change password" className="flex flex-1 items-center justify-center gap-2 rounded-md px-2 py-2 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"><Lock className="h-3.5 w-3.5" />{!collapsed && 'Password'}</button><button onClick={logout} title="Sign out" className="flex flex-1 items-center justify-center gap-2 rounded-md px-2 py-2 text-xs text-muted-foreground hover:bg-red-500/10 hover:text-red-600"><LogOut className="h-3.5 w-3.5" />{!collapsed && 'Sign out'}</button></div>
            </div>
            <ChangePasswordModal isOpen={passwordOpen} onClose={() => setPasswordOpen(false)} />
        </aside>
    );
};
export default Sidebar;
