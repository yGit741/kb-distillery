import { useParams } from "@tanstack/react-router";
import { ProposalList } from "./ProposalList";
import { ReviewScreen } from "./ReviewScreen";

/** /proposals lists them; /proposals/$id reviews one (flag ui.proposals). */
export default function ProposalsScreen() {
  const { id } = useParams({ strict: false }) as { id?: string };
  return id ? <ReviewScreen key={id} id={id} /> : <ProposalList />;
}
