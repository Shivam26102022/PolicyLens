import { describe, expect, it } from "vitest";

const scannedFiles = {
  ...import.meta.glob<string>("../src/**/*.{css,html,js,ts,tsx}", {
    eager: true,
    import: "default",
    query: "?raw",
  }),
  ...import.meta.glob<string>("../dist/assets/**/*.{css,html,js}", {
    eager: true,
    import: "default",
    query: "?raw",
  }),
};
const credentialPatterns = [
  /sk-[A-Za-z0-9]{20,}/,
  /AKIA[A-Z0-9]{16}/,
  /\bBearer\s+[A-Za-z0-9._~+/=-]{24,}/i,
  /(?:OPENAI_API_KEY|MLX_API_KEY)\s*[:=]\s*["'][^"']+["']/,
];

describe("frontend security boundary", () => {
  it("keeps provider credentials and secret canaries out of source and build output", () => {
    expect(Object.keys(scannedFiles).length).toBeGreaterThan(0);

    for (const [path, content] of Object.entries(scannedFiles)) {
      for (const pattern of credentialPatterns) {
        expect(content, path).not.toMatch(pattern);
      }
    }
  });

  it("routes browser network calls through the typed backend API modules", () => {
    for (const [path, content] of Object.entries(scannedFiles)) {
      if (!path.includes("/src/")) continue;
      if (/\bfetch\s*\(/.test(content)) {
        expect(path).toMatch(/\/src\/api\/(client|health)\.ts$/);
      }
      expect(content).not.toMatch(/https?:\/\/api\.openai\.com/i);
      expect(content).not.toMatch(/\/mcp\/(?:tools|resources)\b/i);
    }
  });
});
