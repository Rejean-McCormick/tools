const fs = require('fs');
const path = require('path');

// --- MAPPING BASED ON CSV ANALYSIS ---
const MOVES = [
    {
        dir: 'atlas',
        oldName: 'atlas',             // looking for atlas/atlas.mdx
        newName: 'ui-graph-and-ontology' // Rename to: atlas/ui-graph-and-ontology.mdx
    },
    {
        dir: 'theseus',
        oldName: 'theseus',           // looking for theseus/theseus.mdx
        newName: 'exploration-engine' // Rename to: theseus/exploration-engine.mdx
    }
];

const EXTENSIONS = ['.md', '.mdx'];
const IGNORE_DIRS = ['node_modules', '.git', '.next', 'public'];

/**
 * PHASE 1: RENAME THE FILES
 */
function renameFiles(startDir) {
    console.log('--- Phase 1: Renaming Files to Significant Names ---');

    // Recursive search to find the specific folders "atlas" and "theseus"
    function traverse(currentPath) {
        let items;
        try { items = fs.readdirSync(currentPath); } catch (e) { return; }

        for (const item of items) {
            if (IGNORE_DIRS.includes(item)) continue;
            const fullPath = path.join(currentPath, item);
            let stat;
            try { stat = fs.statSync(fullPath); } catch (e) { continue; }

            if (stat.isDirectory()) {
                // Check if this directory matches one of our targets (e.g. "atlas")
                const moveTarget = MOVES.find(m => m.dir === item.toLowerCase());
                
                if (moveTarget) {
                    // Try to find the file inside (e.g. "atlas.mdx")
                    for (const ext of EXTENSIONS) {
                        const oldFile = moveTarget.oldName + ext;
                        const oldFilePath = path.join(fullPath, oldFile);
                        const newFile = moveTarget.newName + ext;
                        const newFilePath = path.join(fullPath, newFile);

                        if (fs.existsSync(oldFilePath)) {
                            console.log(`✅ Renaming: ${oldFilePath} \n        -> ${newFilePath}`);
                            fs.renameSync(oldFilePath, newFilePath);
                        } else if (fs.existsSync(newFilePath)) {
                            console.log(`ℹ️  Already renamed: ${newFilePath}`);
                        }
                    }
                }
                // Continue recursion
                traverse(fullPath);
            }
        }
    }

    traverse(startDir);
}

/**
 * PHASE 2: UPDATE LINKS
 */
function updateLinks(startDir) {
    console.log('\n--- Phase 2: Updating Links in MDX Content ---');

    function traverse(currentPath) {
        let items;
        try { items = fs.readdirSync(currentPath); } catch (e) { return; }

        for (const item of items) {
            if (IGNORE_DIRS.includes(item)) continue;
            const fullPath = path.join(currentPath, item);
            let stat;
            try { stat = fs.statSync(fullPath); } catch (e) { continue; }

            if (stat.isDirectory()) {
                traverse(fullPath);
            } else if (EXTENSIONS.includes(path.extname(item))) {
                let content = fs.readFileSync(fullPath, 'utf8');
                let changed = false;

                // For each move, replace links like ".../atlas/atlas" with ".../atlas/ui-graph-and-ontology"
                MOVES.forEach(move => {
                    const oldSegment = `${move.dir}/${move.oldName}`; // atlas/atlas
                    const newSegment = `${move.dir}/${move.newName}`; // atlas/ui-graph-and-ontology
                    
                    // Regex finds: (start or /)atlas/atlas(end or / or # or space)
                    const regex = new RegExp(`(^|\\/)${move.dir}\\/${move.oldName}(\\/|$|#)`, 'g');

                    if (regex.test(content)) {
                        console.log(`🔗 Updating link in ${item}: .../${oldSegment} -> .../${newSegment}`);
                        // Replace carefully to keep the surrounding slashes/anchors
                        content = content.replace(regex, (match, p1, p2) => {
                            return `${p1}${newSegment}${p2}`;
                        });
                        changed = true;
                    }
                });

                if (changed) {
                    fs.writeFileSync(fullPath, content, 'utf8');
                }
            }
        }
    }

    traverse(startDir);
}

// EXECUTION
renameFiles(process.cwd());
updateLinks(process.cwd());
console.log('\n✅ Script Finished.');