import DashboardPanel from "../dashboard/DashboardPanel.jsx";
import ResultsPanel from "./ResultsPanel.jsx";
import WorkspaceHeader from "./WorkspaceHeader.jsx";

export default function Workspace(props) {
  const {
    fileName,
    selectedCount,
    loading,
    onBack,
    onNewSearch,
    onExport,
  } = props;

  return (
    <main className="mx-auto flex w-full max-w-[1400px] flex-col gap-6 px-6 py-6">
      <WorkspaceHeader
        fileName={fileName}
        selectedCount={selectedCount}
        loading={loading}
        onBack={onBack}
        onNewSearch={onNewSearch}
        onExport={onExport}
      />
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.7fr)]">
        <ResultsPanel {...props} />
        <DashboardPanel {...props} />
      </div>
    </main>
  );
}
