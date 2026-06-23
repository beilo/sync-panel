import { useState } from "react";
import type { Tree, TreeNode } from "../api";

// 只读文件树。两棵根 (shared-skills / shared-rules)。
// 点文件触发预览; 点目录折叠/展开。canonical 内不应有链接, 链接条目标记。

interface Props {
  tree: Tree;
  selectedRel?: string;
  onSelect: (node: TreeNode, rootName: string) => void;
}

export function FileTree({ tree, selectedRel, onSelect }: Props) {
  return (
    <div className="file-tree" data-testid="file-tree">
      {tree.roots.map((root) => (
        <NodeView
          key={root.name}
          node={root}
          rootName={root.name}
          depth={0}
          selectedRel={selectedRel}
          onSelect={onSelect}
          defaultOpen
        />
      ))}
    </div>
  );
}

function NodeView({
  node,
  rootName,
  depth,
  selectedRel,
  onSelect,
  defaultOpen = false,
}: {
  node: TreeNode;
  rootName: string;
  depth: number;
  selectedRel?: string;
  onSelect: (node: TreeNode, rootName: string) => void;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const isSelected = !node.is_dir && node.rel === selectedRel;

  const onClick = () => {
    if (node.is_dir) {
      setOpen((o) => !o);
    } else {
      onSelect(node, rootName);
    }
  };

  return (
    <div className="tree-node">
      <div
        className={`tree-row ${isSelected ? "selected" : ""}`}
        style={{ paddingLeft: depth * 14 + 4 }}
        onClick={onClick}
        data-testid={`node-${node.rel || node.name}`}
      >
        <span className="tree-icon">
          {node.is_dir ? (open ? "▾" : "▸") : "·"}
        </span>
        <span className="tree-name">{node.name}</span>
        {node.is_link && <span className="tree-link-badge">link</span>}
      </div>
      {node.is_dir && open && node.children && (
        <div className="tree-children">
          {node.children.map((c) => (
            <NodeView
              key={c.rel}
              node={c}
              rootName={rootName}
              depth={depth + 1}
              selectedRel={selectedRel}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}
