import axios from "axios";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

const API = axios.create({
  baseURL: API_BASE_URL,
});

export const searchStandards = async (standard) => {
  const response = await API.post("/standards/search", {
    standards: [standard],
  });

  return Array.isArray(response.data?.results)
    ? response.data.results
    : [];
};

export const searchDocumentStandards = async (rows) => {
  const response = await API.post("/documents/search", { rows });
  return response.data?.results || [];
};

export const uploadExcel = async (file) => {
  const formData = new FormData();

  formData.append("file", file);

  const response = await API.post(
    "/excel/upload",
    formData
  );

  return response.data;
};
export const exportSelectedStandards = async (results) => {
  const response = await API.post(
    "/export/excel",
    results,
    {
      responseType: "blob",
    }
  );

  downloadBlob(response.data, "standards_quotation.xlsx");
};

export const exportLatestYearStandards = async (results) => {
  const response = await API.post(
    "/export/latest-years",
    results,
    {
      responseType: "blob",
    }
  );

  downloadBlob(response.data, "standards_latest_years.xlsx");
};

export const exportNotFoundStandards = async (results) => {
  const response = await API.post(
    "/export/not-found",
    results,
    {
      responseType: "blob",
    }
  );

  downloadBlob(
    response.data,
    "not_found_standards.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
  );
};

export const exportFoundAndNotFoundBundle = async (
  quotationResults,
  allResults
) => {
  const response = await API.post(
    "/export/found-and-not-found",
    {
      quotation_results: quotationResults,
      all_results: allResults,
    },
    {
      responseType: "blob",
    }
  );

  downloadBlob(response.data, "standards_found_and_not_found.zip", "application/zip");
};

export const exportBothStandardFiles = async (
  quotationResults,
  latestYearResults
) => {
  const response = await API.post(
    "/export/both",
    {
      quotation_results: quotationResults,
      latest_year_results: latestYearResults,
    },
    {
      responseType: "blob",
    }
  );

  downloadBlob(response.data, "standards_exports.zip", "application/zip");
};

const downloadBlob = (data, filename, contentType) => {
  const blob = new Blob(
    [data],
    {
      type:
        contentType ||
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
  );

  const url = window.URL.createObjectURL(blob);

  const link = document.createElement("a");

  link.href = url;
  link.download = filename;

  document.body.appendChild(link);
  link.click();

  link.remove();

  window.setTimeout(() => {
    window.URL.revokeObjectURL(url);
  }, 60000);
};
