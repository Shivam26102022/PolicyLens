import { getApiBaseUrl } from "../api/health";

export interface PdfSourceOption {
  id: string;
  label: string;
  title: string;
  canonicalUri: string;
  downloadUri: string;
}

export interface ResolvedPdfSource {
  uri: string;
  title: string;
}

export const pdfSources: PdfSourceOption[] = [
  {
    id: "wb-india-skills-programs-2015",
    label: "India skills report (2015)",
    title:
      "Labor Market Impacts and Effectiveness of Skills Development Programs in 5 States in India",
    canonicalUri:
      "https://documents.worldbank.org/en/publication/documents-reports/documentdetail/798601468034846280",
    downloadUri:
      "https://documents1.worldbank.org/curated/en/798601468034846280/pdf/94682-Change-in-Title-Final-Revised-Output-Skill-Report-5-States.pdf",
  },
  {
    id: "wb-malaysia-informal-employment-2024",
    label: "Malaysia informal-employment report (2024)",
    title:
      "Informal Employment in Malaysia: Trends, Challenges and Opportunities for Reform",
    canonicalUri:
      "https://documents.worldbank.org/en/publication/documents-reports/documentdetail/099022124104015011",
    downloadUri:
      "https://documents1.worldbank.org/curated/en/099022124104015011/pdf/P1810931e836170db184871b5fe7b37157c.pdf",
  },
  {
    id: "wb-indonesia-jobs-action-2018",
    label: "Indonesia Jobs Action Program (2018)",
    title: "Indonesia Jobs Action Program: Towards Win-Win",
    canonicalUri:
      "https://documents.worldbank.org/en/publication/documents-reports/documentdetail/361621624942826086",
    downloadUri:
      "https://documents1.worldbank.org/curated/en/361621624942826086/pdf/Indonesia-Jobs-Action-Program-Towards-Win-Win-A-Labor-Reform-Strategy-to-Benefit-All.pdf",
  },
  {
    id: "wb-singapore-workforce-development-2012",
    label: "Singapore SABER workforce report (2012)",
    title: "SABER Workforce Development Country Report: Singapore",
    canonicalUri:
      "https://documents.worldbank.org/en/publication/documents-reports/documentdetail/101071468299971244",
    downloadUri:
      "https://documents1.worldbank.org/curated/en/101071468299971244/pdf/799250WP0SABER0Box0379795B00PUBLIC0.pdf",
  },
];

function safeHttpUrl(value: string | null | undefined): URL | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    if (
      !["http:", "https:"].includes(url.protocol) ||
      url.username.length > 0 ||
      url.password.length > 0
    ) {
      return null;
    }
    return url;
  } catch {
    return null;
  }
}

function sameResource(left: string, right: string): boolean {
  const leftUrl = safeHttpUrl(left);
  const rightUrl = safeHttpUrl(right);
  if (!leftUrl || !rightUrl) return false;
  const normalizedPath = (path: string) => path.replace(/\/+$/u, "");
  return (
    leftUrl.origin === rightUrl.origin &&
    normalizedPath(leftUrl.pathname) === normalizedPath(rightUrl.pathname)
  );
}

function localPdfUri(sourceId: string): string {
  const apiBase = getApiBaseUrl().replace(/\/+$/u, "");
  return `${apiBase}/sources/${encodeURIComponent(sourceId)}/pdf`;
}

export function resolvePdfSource(
  uri: string | null | undefined,
  sourceId?: string,
  allowUnregisteredPdf = false,
): ResolvedPdfSource | null {
  const knownSource = pdfSources.find((source) => source.id === sourceId);
  if (
    knownSource &&
    (!uri ||
      sameResource(uri, knownSource.canonicalUri) ||
      sameResource(uri, knownSource.downloadUri))
  ) {
    return { uri: localPdfUri(knownSource.id), title: knownSource.title };
  }

  const url = safeHttpUrl(uri);
  if (!url) return null;

  const knownUri = pdfSources.find(
    (source) =>
      sameResource(url.toString(), source.canonicalUri) ||
      sameResource(url.toString(), source.downloadUri),
  );
  if (knownUri) return { uri: localPdfUri(knownUri.id), title: knownUri.title };

  if (!allowUnregisteredPdf || !url.pathname.toLowerCase().endsWith(".pdf")) {
    return null;
  }
  return {
    uri: url.toString(),
    title: url.pathname.split("/").at(-1) || "Source PDF",
  };
}

export function pdfViewerUrl(
  source: ResolvedPdfSource,
  pageStart: number | null,
  excerpt: string,
): string {
  const url = new URL(source.uri, window.location.href);
  if (pageStart === null) return url.toString();

  const search = excerpt.replace(/\s+/gu, " ").trim().slice(0, 160);
  url.hash = search
    ? `page=${pageStart}&search=${encodeURIComponent(search)}&phrase=true`
    : `page=${pageStart}`;
  return url.toString();
}
