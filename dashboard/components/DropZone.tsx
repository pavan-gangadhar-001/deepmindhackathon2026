"use client";

import { useCallback, useRef, useState } from "react";

type DropZoneProps = {
  onPath: (path: string) => void;
  onZipFile?: (file: File | null) => void;
};

function isZipFile(file: File) {
  return file.name.toLowerCase().endsWith(".zip") || file.type === "application/zip";
}

export function DropZone({ onPath, onZipFile }: DropZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [localPath, setLocalPath] = useState("");
  const [zipName, setZipName] = useState<string | null>(null);

  const pickZip = useCallback(
    (file: File | null) => {
      if (!file) {
        setZipName(null);
        onZipFile?.(null);
        return;
      }
      if (!isZipFile(file)) {
        return;
      }
      setZipName(file.name);
      setLocalPath("");
      onPath("");
      onZipFile?.(file);
    },
    [onPath, onZipFile]
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) {
        pickZip(file);
      }
    },
    [pickZip]
  );

  return (
    <div className="space-y-3">
      <input
        ref={inputRef}
        type="file"
        accept=".zip,application/zip"
        className="hidden"
        onChange={(e) => pickZip(e.target.files?.[0] ?? null)}
      />

      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`w-full rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
          dragging
            ? "border-action-blue bg-action-blue/5"
            : "border-hairline bg-stone/50 hover:border-action-blue/40"
        }`}
      >
        <p className="text-[15px] font-medium text-ink">
          {zipName ? `Selected: ${zipName}` : "Drop a project .zip here"}
        </p>
        <p className="mt-1 text-[13px] text-ink-muted">
          Click to browse, or drag and drop a zip file (max 100 MB)
        </p>
        {zipName && (
          <p className="mt-2 text-[12px] text-action-blue">
            Zip will be uploaded when you start the session
          </p>
        )}
      </button>

      <div className="relative">
        <div className="absolute inset-x-0 top-1/2 h-px bg-hairline" />
        <p className="relative mx-auto w-fit bg-canvas px-3 text-[12px] text-ink-muted">
          or local folder path
        </p>
      </div>

      <input
        type="text"
        value={localPath}
        onChange={(e) => {
          const value = e.target.value;
          setLocalPath(value);
          if (value.trim()) {
            setZipName(null);
            onZipFile?.(null);
          }
          onPath(value);
        }}
        placeholder="C:\path\to\your\app or ./demo_app"
        className="w-full rounded-xl border border-hairline bg-canvas px-4 py-3 text-[14px] text-ink outline-none ring-action-blue/30 focus:ring-2"
      />
    </div>
  );
}
