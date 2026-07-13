/**
 * IBM-standard OS strings for IBM VPC / RVTools compatibility.
 * Mirrors the output values of _OS_NORMALIZATION in api/services/ai_normalizer.py.
 * Keep both lists in sync when adding new OS mappings.
 *
 * x86 VPC SAP/SQL families map to specific IBM Cloud Cost Estimator OS families.
 * AIX / IBM i entries are automatically routed to the PowerVS export.
 */
export const IBM_OS_OPTIONS: string[] = [
  // ── Red Hat Enterprise Linux ────────────────────────────────────────────────
  'Red Hat Enterprise Linux 9 (64-bit)',
  'Red Hat Enterprise Linux 8 (64-bit)',
  'Red Hat Enterprise Linux 7 (64-bit)',
  'Red Hat Enterprise Linux 6 (64-bit)',
  // SAP variant (x86 VPC — IBM Cloud Cost Estimator OS family)
  'Red Hat Enterprise Linux for SAP (64-bit)',
  // ── SUSE Linux Enterprise ───────────────────────────────────────────────────
  'SUSE Linux Enterprise 15 (64-bit)',
  'SUSE Linux Enterprise 12 (64-bit)',
  // SAP variant (x86 VPC — IBM Cloud Cost Estimator OS family)
  'SUSE Linux Enterprise Server for SAP (64-bit)',
  // ── Ubuntu ──────────────────────────────────────────────────────────────────
  'Ubuntu Linux (64-bit)',
  // ── Debian ──────────────────────────────────────────────────────────────────
  'Debian GNU/Linux (64-bit)',
  // ── CentOS ──────────────────────────────────────────────────────────────────
  'CentOS Linux (64-bit)',
  'CentOS 4/5/6/7 (64-bit)',
  // ── Oracle Linux ────────────────────────────────────────────────────────────
  'Oracle Linux 8 and later (64-bit)',
  'Oracle Linux 7 (64-bit)',
  // ── Rocky Linux ─────────────────────────────────────────────────────────────
  'Rocky Linux (64-bit)',
  // ── AlmaLinux ───────────────────────────────────────────────────────────────
  'AlmaLinux (64-bit)',
  // ── Fedora CoreOS ───────────────────────────────────────────────────────────
  'Fedora CoreOS (64-bit)',
  // ── Microsoft Windows Server ─────────────────────────────────────────────────
  'Microsoft Windows Server 2022 (64-bit)',
  'Microsoft Windows Server 2019 (64-bit)',
  'Microsoft Windows Server 2016 (64-bit)',
  'Microsoft Windows Server 2012 R2 (64-bit)',
  'Microsoft Windows Server 2012 (64-bit)',
  'Microsoft Windows Server 2008 R2 (64-bit)',
  'Microsoft Windows Server 2008 (64-bit)',
  // Windows with SQL Server (x86 VPC — IBM Cloud Cost Estimator OS family)
  'Microsoft Windows Server with SQL Server (64-bit)',
  // ── AIX / IBM i (PowerVS — routed to PowerVS export automatically) ───────────
  'IBM AIX 7.x',
  'IBM AIX 6.x',
  'IBM i (OS/400)',
  // ── Other ───────────────────────────────────────────────────────────────────
  'Other Linux (64-bit)',
  'Other (64-bit)',
];

/** Short display label (strip the " (64-bit)" suffix for compact display) */
export function shortOsLabel(os: string): string {
  return os.replace(/ \(64-bit\)/i, '');
}
