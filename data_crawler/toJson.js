const fs = require('fs');
const vm = require('vm');
const path = require('path');

const inputFile = path.join('phap-dien/jsonData.js');
const outputDir = 'phap-dien';

const source = fs.readFileSync(inputFile, 'utf8');

const sandbox = { window: {}, global: {} };
vm.createContext(sandbox);
vm.runInContext(source, sandbox);

const chude = sandbox.jdChuDe || sandbox.window.jdChuDe || sandbox.global.jdChuDe;
const demuc = sandbox.jdDeMuc || sandbox.window.jdDeMuc || sandbox.global.jdDeMuc;
const treeNode = sandbox.jdAllTree || sandbox.window.jdAllTree || sandbox.global.jdAllTree;

if (!chude || !demuc || !treeNode) {
  throw new Error('Khong doc duoc jdChuDe, jdDeMuc, hoac jdAllTree tu jsonData.js');
}

fs.writeFileSync(path.join(outputDir, 'chude.json'), JSON.stringify(chude, null, 2), 'utf8');
fs.writeFileSync(path.join(outputDir, 'demuc.json'), JSON.stringify(demuc, null, 2), 'utf8');
fs.writeFileSync(path.join(outputDir, 'treeNode.json'), JSON.stringify(treeNode, null, 2), 'utf8');

console.log('Da tao chude.json, demuc.json, treeNode.json');
