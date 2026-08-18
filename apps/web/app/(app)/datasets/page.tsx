import { DatasetsView } from "./DatasetsView";

export const metadata = {
  title: "Datasets — Signal Foundry",
};

// Static export (GitHub Pages, no server): live backend state can only be read client-side,
// against NEXT_PUBLIC_API_URL — see DatasetsView.
export default function DatasetsPage() {
  return <DatasetsView />;
}
