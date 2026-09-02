import type { ReactNode, ElementType } from 'react';
import { Inbox, Loader2 } from 'lucide-react';

export const PageHeader = ({
    eyebrow,
    title,
    description,
    actions,
}: {
    eyebrow?: string;
    title: string;
    description?: string;
    actions?: ReactNode;
}) => (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
            {eyebrow && <p className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-primary">{eyebrow}</p>}
            <h1 className="text-3xl font-semibold tracking-[-0.035em] text-foreground sm:text-[2.15rem]">{title}</h1>
            {description && <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
);

export const MetricCard = ({
    label,
    value,
    detail,
    icon: Icon,
    tone = 'default',
}: {
    label: string;
    value: string | number;
    detail?: string;
    icon: ElementType;
    tone?: 'default' | 'success' | 'warning' | 'danger';
}) => {
    const tones = {
        default: 'text-primary bg-primary/10',
        success: 'text-emerald-700 dark:text-emerald-400 bg-emerald-500/10',
        warning: 'text-amber-700 dark:text-amber-400 bg-amber-500/10',
        danger: 'text-red-700 dark:text-red-400 bg-red-500/10',
    };
    return (
        <div className="rounded-xl border border-border/70 bg-card p-5 shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
            <div className="flex items-start justify-between gap-4">
                <div>
                    <p className="text-sm font-medium text-muted-foreground">{label}</p>
                    <p className="mt-3 text-3xl font-semibold tracking-[-0.04em]">{value}</p>
                    {detail && <p className="mt-1.5 text-xs text-muted-foreground">{detail}</p>}
                </div>
                <div className={`rounded-lg p-2.5 ${tones[tone]}`}><Icon className="h-5 w-5" /></div>
            </div>
        </div>
    );
};

export const SectionCard = ({
    title,
    description,
    action,
    children,
    className = '',
}: {
    title?: string;
    description?: string;
    action?: ReactNode;
    children: ReactNode;
    className?: string;
}) => (
    <section className={`overflow-hidden rounded-xl border border-border/70 bg-card shadow-[0_1px_2px_rgba(0,0,0,0.03)] ${className}`}>
        {(title || action) && (
            <div className="flex items-start justify-between gap-4 border-b border-border/60 px-5 py-4">
                <div>
                    {title && <h2 className="text-base font-semibold tracking-[-0.015em]">{title}</h2>}
                    {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
                </div>
                {action}
            </div>
        )}
        {children}
    </section>
);

const statusTone = (value: string) => {
    const token = String(value || '').toLowerCase();
    if (['running', 'qualified', 'transferred', 'completed', 'success', 'answered'].some(x => token.includes(x))) {
        return 'border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400';
    }
    if (['paused', 'callback', 'pending', 'scheduled', 'draft'].some(x => token.includes(x))) {
        return 'border-amber-500/20 bg-amber-500/10 text-amber-700 dark:text-amber-400';
    }
    if (['failed', 'error', 'do_not_call', 'do not call', 'canceled', 'declined'].some(x => token.includes(x))) {
        return 'border-red-500/20 bg-red-500/10 text-red-700 dark:text-red-400';
    }
    return 'border-border bg-muted/70 text-muted-foreground';
};

export const StatusBadge = ({ value, label }: { value: string; label?: string }) => (
    <span className={`inline-flex items-center rounded-md border px-2 py-1 text-xs font-semibold ${statusTone(value)}`}>
        {label || String(value || 'Unknown').replace(/_/g, ' ')}
    </span>
);

export const EmptyState = ({ title, description, action }: { title: string; description: string; action?: ReactNode }) => (
    <div className="flex min-h-48 flex-col items-center justify-center px-6 py-10 text-center">
        <div className="mb-4 rounded-full bg-muted p-3"><Inbox className="h-5 w-5 text-muted-foreground" /></div>
        <h3 className="text-sm font-semibold">{title}</h3>
        <p className="mt-1 max-w-md text-sm leading-6 text-muted-foreground">{description}</p>
        {action && <div className="mt-5">{action}</div>}
    </div>
);

export const PageLoading = ({ label = 'Loading workspace' }: { label?: string }) => (
    <div className="flex min-h-64 items-center justify-center gap-3 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> {label}
    </div>
);

export const primaryButton = 'inline-flex h-9 items-center justify-center gap-2 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:pointer-events-none disabled:opacity-50';
export const secondaryButton = 'inline-flex h-9 items-center justify-center gap-2 rounded-md border border-border bg-card px-3 text-sm font-medium transition-colors hover:bg-accent';
export const inputClass = 'h-9 w-full rounded-md border border-input bg-background px-3 text-sm outline-none transition-shadow placeholder:text-muted-foreground focus:ring-2 focus:ring-primary/20 focus:border-primary';
