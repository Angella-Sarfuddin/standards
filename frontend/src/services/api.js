import axios from "axios";

const API = axios.create({
  baseURL: "http://127.0.0.1:8000",
});

export const searchStandards = async (standard) => {
  const response = await API.post("/standards/search", {
    standards: [standard],
  });

  return response.data;
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

  const blob = new Blob(
    [response.data],
    {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
  );

  const url = window.URL.createObjectURL(blob);

  const link = document.createElement("a");

  link.href = url;
  link.download = "standards_quotation.xlsx";

  document.body.appendChild(link);
  link.click();

  link.remove();

  window.URL.revokeObjectURL(url);
};