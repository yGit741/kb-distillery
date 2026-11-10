import { useParams } from "@tanstack/react-router";
import { Inbox } from "./Inbox";
import { ReviewScreen } from "./ReviewScreen";
import "./tours";

/** /proposals is the review inbox; /proposals/$id reviews one (flag ui.proposals). */
export default function ProposalsScreen() {
  const { id } = useParams({ strict: false }) as { id?: string };
  return id ? <ReviewScreen key={id} id={id} /> : <Inbox />;
}
