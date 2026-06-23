import type { FileContent } from "../api";

// 只读预览区。仅展示 canonical 文件内容 (设计要求: 不打开 target/备份作为独立源)。

export function Preview({ file }: { file: FileContent | null }) {
  if (!file) {
    return <div className="preview-empty" data-testid="preview-empty">选择左侧文件查看内容</div>;
  }
  if (file.error) {
    return (
      <div className="preview-error" data-testid="preview-error">
        {file.error}
      </div>
    );
  }
  if (file.is_binary) {
    return <div className="preview-binary">二进制文件, 无法预览 ({file.size} 字节)</div>;
  }
  return (
    <div className="preview-wrap" data-testid="preview-content">
      <div className="preview-path">{file.path}</div>
      {file.truncated && <div className="preview-trunc">⚠ 内容过大已截断</div>}
      <pre className="preview-pre">{file.content}</pre>
    </div>
  );
}
