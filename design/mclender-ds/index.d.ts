import type * as React from 'react';
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> { variant?: 'primary' | 'secondary' | 'quiet' | 'danger'; size?: 'md' | 'sm' }
export declare function Button(props: ButtonProps): React.ReactElement;
export type LoanStatus = 'DRAFT' | 'PENDING' | 'APPROVED' | 'REJECTED' | 'ACTIVE' | 'ARREARS' | 'ARREARS_LATE' | 'CLOSED' | 'WRITTEN_OFF' | 'PAID' | 'DUE' | 'OVERDUE' | 'APPROVE' | 'REFER' | 'DECLINE';
export interface StatusPillProps { status: LoanStatus; days?: number; label?: string; tone?: 'neutral' | 'info' | 'brand' | 'success' | 'warning' | 'danger' | 'gold' }
export declare function StatusPill(props: StatusPillProps): React.ReactElement;
export interface MoneyProps { amount: number | string; size?: 'md' | 'lg'; tone?: 'gold' | 'danger' | 'success' | 'warning' | 'muted'; decimals?: number; className?: string }
export declare function Money(props: MoneyProps): React.ReactElement;
export interface StatTileProps { label: string; value: React.ReactNode; delta?: string; deltaTone?: 'success' | 'warning' | 'danger' | 'muted'; hint?: string; emphasis?: 'gold' }
export declare function StatTile(props: StatTileProps): React.ReactElement;
export interface FieldProps { label: string; id?: string; type?: string; inputMode?: string; placeholder?: string; defaultValue?: string; prefix?: string; hint?: string; error?: string; optional?: boolean; children?: React.ReactNode }
export declare function Field(props: FieldProps): React.ReactElement;
export interface DataTableColumn<R> { key: string; label: string; align?: 'left' | 'right'; render?: (row: R) => React.ReactNode }
export interface DataTableProps<R = any> { columns: DataTableColumn<R>[]; rows: R[]; caption?: string; selectedId?: string | number; onRowClick?: (row: R) => void }
export declare function DataTable<R>(props: DataTableProps<R>): React.ReactElement;
export interface LoanStepperProps { current: number; steps?: string[] }
export declare function LoanStepper(props: LoanStepperProps): React.ReactElement;
export interface AssessmentCardProps { recommendation: 'APPROVE' | 'REFER' | 'DECLINE'; score: number; dti: number; maxDti?: number; monthlyPayment: number; cap: number; notes?: string[] }
export declare function AssessmentCard(props: AssessmentCardProps): React.ReactElement;
export declare function formatKina(amount: number | string, opts?: { decimals?: number; currency?: boolean }): string;
declare global { interface Window { McLender: { Button: typeof Button; StatusPill: typeof StatusPill; Money: typeof Money; StatTile: typeof StatTile; Field: typeof Field; DataTable: typeof DataTable; LoanStepper: typeof LoanStepper; AssessmentCard: typeof AssessmentCard; formatKina: typeof formatKina } } }
