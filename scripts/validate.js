const fs = require('fs');
const path = require('path');

const repoDir = 'C:\\Users\\keych\\Documents\\antigravity\\madoromi-kisetsucho-data';
const jsonPath = path.join(repoDir, 'data', 'seasonal_data_v1.json');
const reportPath = path.join(repoDir, 'data', 'update_report.json');

if (!fs.existsSync(jsonPath)) {
  console.error(`Error: ${jsonPath} does not exist.`);
  process.exit(1);
}

let data;
try {
  data = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
} catch (e) {
  console.error(`Error decoding JSON: ${e}`);
  process.exit(1);
}

const errors = [];
const warningsList = [];

if (!data.hasOwnProperty('dataVersion')) errors.push("Missing 'dataVersion' in root.");
if (!data.hasOwnProperty('generatedAt')) errors.push("Missing 'generatedAt' in root.");
if (!data.hasOwnProperty('items') || !Array.isArray(data.items)) {
  errors.push("'items' is missing or not a list.");
}

const items = data.items || [];
const seenIds = new Set();
const categoryCounts = {};
const statusCounts = {};
let checkingCount = 0;

const allowedCategories = new Set(["NATURE", "EVENT", "ASTRONOMY", "SEASONAL_CUSTOM"]);
const allowedStatuses = new Set([
  "UPCOMING", "PEAK_SOON", "BEST_SEASON", "ONGOING", 
  "PAST_PEAK", "ENDED", "CHECKING", "CANCELLED_OR_CHANGED"
]);

function checkSecret(val) {
  if (typeof val !== 'string') return false;
  
  // Google API Key
  const googleKey = /AIza[0-9A-Za-z-_]{35}/;
  if (googleKey.test(val)) return true;
  
  // Generic Secret Patterns
  const patterns = [
    /api[-_]?key/i,
    /secret/i,
    /token/i,
    /password/i
  ];
  
  // High entropy strings longer than 40 chars
  if (val.length > 40 && /^[A-Za-z0-9+/=_-]+$/.test(val)) {
    for (const p of patterns) {
      if (p.test(val)) return true;
    }
  }
  return false;
}

function checkObjectForSecrets(obj, itemId, prefix = '') {
  for (const k in obj) {
    if (!obj.hasOwnProperty(k)) continue;
    const v = obj[k];
    const pathStr = prefix ? `${prefix}.${k}` : k;
    
    if (checkSecret(v)) {
      errors.push(`Possible API Key/Secret detected in item '${itemId}' field '${pathStr}': ${v}`);
    }
    
    if (v && typeof v === 'object') {
      if (Array.isArray(v)) {
        v.forEach((entry, idx) => {
          if (entry && typeof entry === 'object') {
            checkObjectForSecrets(entry, itemId, `${pathStr}[${idx}]`);
          } else if (checkSecret(entry)) {
            errors.push(`Possible API Key/Secret detected in item '${itemId}' field '${pathStr}[${idx}]': ${entry}`);
          }
        });
      } else {
        checkObjectForSecrets(v, itemId, pathStr);
      }
    }
  }
}

items.forEach((item, i) => {
  const itemId = item.id || `index_${i}`;
  
  if (seenIds.has(itemId)) {
    errors.push(`Duplicate item ID: '${itemId}'`);
  }
  seenIds.add(itemId);
  
  if (!item.title) {
    errors.push(`Item '${itemId}' has empty title.`);
  }
  
  const cat = item.category;
  if (!allowedCategories.has(cat)) {
    errors.push(`Item '${itemId}' has invalid category: '${cat}'`);
  } else {
    categoryCounts[cat] = (categoryCounts[cat] || 0) + 1;
  }
  
  if (!item.subCategory) {
    errors.push(`Item '${itemId}' has empty subCategory.`);
  }
  
  const status = item.commonStatus;
  if (!allowedStatuses.has(status)) {
    errors.push(`Item '${itemId}' has invalid commonStatus: '${status}'`);
  } else {
    statusCounts[status] = (statusCounts[status] || 0) + 1;
    if (status === 'CHECKING') {
      checkingCount++;
    }
  }
  
  const dateInfo = item.dateInfo || {};
  if (!dateInfo.displayText && !dateInfo.displayDate) {
    errors.push(`Item '${itemId}' misses both dateInfo.displayText and dateInfo.displayDate.`);
  }
  
  const loc = item.location || {};
  if (!loc.displayText && !loc.prefecture && !loc.region) {
    errors.push(`Item '${itemId}' misses location.displayText/prefecture/region.`);
  }
  
  const sources = item.sources || [];
  if (!Array.isArray(sources) || sources.length === 0) {
    errors.push(`Item '${itemId}' must have at least one source.`);
  } else {
    sources.forEach((src, sIdx) => {
      if (!src.url) {
        errors.push(`Source ${sIdx} in Item '${itemId}' misses URL.`);
      }
    });
  }
  
  let lastVerified = item.lastVerifiedAt;
  if (!lastVerified) {
    const hasVer = sources.some(src => src.lastVerifiedAt);
    if (!hasVer) {
      errors.push(`Item '${itemId}' misses lastVerifiedAt in root and all sources.`);
    }
  }
  
  if (status === 'CHECKING') {
    let hasCheckingLabel = false;
    sources.forEach(src => {
      const label = src.certaintyLabel || '';
      if (['確認中', '公式発表待ち', '未発表', '情報確認中', '順次確認'].some(w => label.includes(w))) {
        hasCheckingLabel = true;
      }
    });
    if (!hasCheckingLabel) {
      warningsList.push(`Item '${itemId}' is CHECKING but certaintyLabel does not mention '確認中' or '公式発表待ち' etc.`);
    }
    
    const notif = item.notificationMeta || {};
    if (notif.notifyEnabled === true) {
      const priority = notif.priority || 3;
      if (priority > 1) {
        warningsList.push(`Item '${itemId}' is CHECKING but has notifyEnabled=true and high priority=${priority}.`);
      }
    }
  }
  
  if (status === 'CANCELLED_OR_CHANGED') {
    const warnings = item.warnings || [];
    const hasHighSeverity = warnings.some(w => w.severity === 'high');
    if (!hasHighSeverity) {
      warningsList.push(`Item '${itemId}' is CANCELLED_OR_CHANGED but misses a high severity warning.`);
    }
  }
  
  checkObjectForSecrets(item, itemId);
});

const success = errors.length === 0;

const offset = 9 * 60; // Asia/Tokyo
const localTime = new Date(Date.now() + offset * 60 * 1000);
const runAt = localTime.toISOString().replace('Z', '+09:00');

const report = {
  validationSuccess: success,
  validationErrors: errors,
  validationWarnings: warningsList,
  runAt: runAt,
  summary: {
    dataVersion: data.dataVersion || "unknown",
    generatedAt: data.generatedAt || "unknown",
    schemaVersion: data.schemaVersion || "unknown",
    totalItems: items.length,
    categoryCounts: categoryCounts,
    statusCounts: statusCounts,
    checkingCount: checkingCount
  }
};

try {
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2), 'utf8');
} catch (e) {
  console.error(`Error writing report: ${e}`);
}

if (!success) {
  console.log("=== Validation Failed ===");
  errors.forEach(err => console.log(`- ${err}`));
  console.log(`Total Errors: ${errors.length}`);
  process.exit(1);
}

console.log("=== Validation Success ===");
console.log(`Checked ${items.length} items.`);
if (warningsList.length > 0) {
  console.log(`Warnings (${warningsList.length}):`);
  warningsList.forEach(warn => console.log(`- ${warn}`));
}
process.exit(0);
