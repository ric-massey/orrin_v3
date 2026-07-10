import { Navigate } from "react-router-dom";
import { readMode } from "@/lib/mode";

// C6: the default landing follows the mode flag (unset counts as workshop, so
// the /face default is unchanged for every existing user). Read at render time
// — the mode can change within a session via Settings.
export default function ModeRedirect() {
  return <Navigate to={readMode() === "companion" ? "/orrin" : "/face"} replace />;
}
