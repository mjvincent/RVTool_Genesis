import { readFileSync } from "fs";

const JONESMI = ".bob/tmp/xlsx-dumps/jonesmi@us.ibm.com-RVTools_x86_Windows_Servers_20216_Subset_20260710_185735-2026-07-10_19-01-23-a566e1211c9761da";
const RVTOOLS = ".bob/tmp/xlsx-dumps/RVToolsPure_x86_Windows_Servers_20216_Subset_20260710_185738-ee8e43bf8be6d3b5";

const ps = JSON.parse(readFileSync(`${JONESMI}/Project_Settings.json`, "utf-8"));
const ex = JSON.parse(readFileSync(`${JONESMI}/Exceptions.json`, "utf-8"));
const dd = JSON.parse(readFileSync(`${JONESMI}/Data_Domains.json`, "utf-8"));
const vi = JSON.parse(readFileSync(`${RVTOOLS}/vInfo.json`, "utf-8"));
const vn = JSON.parse(readFileSync(`${RVTOOLS}/vNetwork.json`, "utf-8"));
const vp = JSON.parse(readFileSync(`${RVTOOLS}/vPartition.json`, "utf-8"));

// Identify unique Requirement Types in Project Settings
const psIdx = Object.fromEntries(ps.headers.map((h, i) => [h, i]));
const reqTypes = [...new Set(ps.rows.map(r => r[psIdx["Requirement Type"]]).filter(Boolean))];

// Show all rows grouped by Requirement Type
const byType = {};
for (const row of ps.rows) {
  const t = row[psIdx["Requirement Type"]] || "(null)";
  if (!byType[t]) byType[t] = [];
  byType[t].push(row);
}

// For Compute rows: show all non-null columns for first 3 entries
const computeRows = byType["Compute"] || [];
const computeSample = computeRows.slice(0, 5).map(row => {
  const obj = {};
  ps.headers.forEach((h, i) => { if (row[i] !== null) obj[h] = row[i]; });
  return obj;
});

// For Data Volume rows: show all non-null columns for first 3 entries
const dvRows = byType["Data Volume"] || [];
const dvSample = dvRows.slice(0, 3).map(row => {
  const obj = {};
  ps.headers.forEach((h, i) => { if (row[i] !== null) obj[h] = row[i]; });
  return obj;
});

// Zone and Subnet rows
const zoneRows = (byType["Zone"] || []).slice(0, 2).map(row => {
  const obj = {};
  ps.headers.forEach((h, i) => { if (row[i] !== null) obj[h] = row[i]; });
  return obj;
});
const subnetRows = (byType["Subnet"] || []).slice(0, 2).map(row => {
  const obj = {};
  ps.headers.forEach((h, i) => { if (row[i] !== null) obj[h] = row[i]; });
  return obj;
});

// Look at corresponding RVTools vInfo rows by VM name
const viIdx = Object.fromEntries(vi.headers.map((h, i) => [h, i]));
const vnIdx = Object.fromEntries(vn.headers.map((h, i) => [h, i]));
const vpIdx = Object.fromEntries(vp.headers.map((h, i) => [h, i]));

// Find the VM names that appear in both files
const jonesmiVMs = new Set(computeRows.map(r => r[psIdx["Compute name"]]).filter(Boolean));
const rvtoolsVMs = vi.rows.map(r => r[viIdx["VM"]]);
const intersection = rvtoolsVMs.filter(v => jonesmiVMs.has(v)).slice(0, 5);

// For each intersecting VM, show RVTools fields alongside jonesmi fields
const mapping = intersection.map(vmName => {
  const rvRow = vi.rows.find(r => r[viIdx["VM"]] === vmName);
  const jRow = computeRows.find(r => r[psIdx["Compute name"]] === vmName);
  
  const rvObj = {};
  vi.headers.forEach((h, i) => { rvObj[h] = rvRow?.[i] ?? null; });
  
  const jObj = {};
  ps.headers.forEach((h, i) => { if (jRow?.[i] !== null) jObj[h] = jRow?.[i] ?? null; });
  
  // Network row for this VM
  const netRow = vn.rows.find(r => r[vnIdx["VM"]] === vmName);
  const netObj = {};
  if (netRow) vn.headers.forEach((h, i) => { if (netRow[i] !== null) netObj[h] = netRow[i]; });
  
  // Partition rows for this VM
  const partRows = vp.rows.filter(r => r[vpIdx["VM"]] === vmName);
  const partObjs = partRows.map(pr => {
    const o = {};
    vp.headers.forEach((h, i) => { if (pr[i] !== null) o[h] = pr[i]; });
    return o;
  });
  
  // Data volume rows from jonesmi for this VM (rows after the Compute row until next Compute row)
  const cIdx = computeRows.findIndex(r => r[psIdx["Compute name"]] === vmName);
  // Find DV rows that are adjacent — look in full ps.rows
  const psRowIdx = ps.rows.findIndex(r => r[psIdx["Compute name"]] === vmName && r[psIdx["Requirement Type"]] === "Compute");
  const dvForVM = [];
  for (let i = psRowIdx + 1; i < ps.rows.length; i++) {
    const rt = ps.rows[i][psIdx["Requirement Type"]];
    if (rt === "Compute" || rt === "Zone" || rt === "Subnet") break;
    if (rt === "Data Volume") {
      const o = {};
      ps.headers.forEach((h, i2) => { if (ps.rows[i][i2] !== null) o[h] = ps.rows[i][i2]; });
      dvForVM.push(o);
    }
  }
  
  return { vmName, rvtools_vInfo: rvObj, rvtools_vNetwork: netObj, rvtools_vPartition: partObjs, jonesmi_compute: jObj, jonesmi_data_volumes: dvForVM };
});

// Profile mapping: what IBM VPC profile does each CPU/RAM combo map to?
// From the sample: 8 CPU / 16384 MB -> cxf-8x16 (Flex-Compute), 8 CPU / 32768 MB -> bxf-8x32 (Flex-Balanced)
const profileMap = {};
for (const vm of mapping) {
  const cpus = vm.rvtools_vInfo["CPUs"];
  const memMB = vm.rvtools_vInfo["Memory"];
  const memGB = Math.round(memMB / 1024);
  const key = `${cpus}cpu_${memGB}gb`;
  profileMap[key] = {
    cpus, memMB, memGB,
    "Compute Category VS": vm.jonesmi_compute["Compute Category VS"],
    "Compute Family VS": vm.jonesmi_compute["Compute Family VS"],
  };
}

// Issues: what values appear and what do they mean?
const allIssues = [...new Set(ps.rows.map(r => r[psIdx["Issues"]]).filter(Boolean))];
const exIssues = [...new Set(ex.rows.map(r => r[psIdx["Issues"]]).filter(Boolean))];

// Summary of Exceptions vs Project Settings
const exComputeRows = ex.rows.filter(r => r[psIdx["Requirement Type"]] === "Compute");
const exSample = exComputeRows.slice(0, 3).map(row => {
  const obj = {};
  ps.headers.forEach((h, i) => { if (row[i] !== null) obj[h] = row[i]; });
  return obj;
});

console.log(JSON.stringify({
  requirement_types: reqTypes,
  count_by_type: Object.fromEntries(Object.entries(byType).map(([k, v]) => [k, v.length])),
  compute_sample: computeSample,
  data_volume_sample: dvSample,
  zone_rows: zoneRows,
  subnet_rows: subnetRows,
  vm_mapping_examples: mapping,
  profile_map: profileMap,
  all_issues_in_project_settings: allIssues,
  exceptions_sheet: { compute_count: exComputeRows.length, sample: exSample, issues: exIssues },
  data_domains_headers: dd.headers,
  data_domains_row_count: dd.rows.length,
}, null, 2));
