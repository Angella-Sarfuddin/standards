import DashboardPanel from "../dashboard/DashboardPanel.jsx";
import ResultsPanel from "./ResultsPanel.jsx";
import WorkspaceHeader from "./WorkspaceHeader.jsx";

export default function Workspace(props) {
  const {
    fileName,
    onBack,
    onNewSearch,
  } = props;

  return (
    <main className="mx-auto flex w-full max-w-[1600px] min-w-0 flex-col gap-5 px-4 py-5 sm:gap-6 sm:px-6 sm:py-7 lg:px-8">
      <WorkspaceHeader
        fileName={fileName}
        onBack={onBack}
        onNewSearch={onNewSearch}
      />
      <div className="grid min-w-0 items-start gap-4 xl:grid-cols-[minmax(0,1.8fr)_minmax(320px,0.72fr)] xl:gap-5">
        <ResultsPanel {...props} />
        <DashboardPanel {...props} />
      </div>
    </main>
  );
}
