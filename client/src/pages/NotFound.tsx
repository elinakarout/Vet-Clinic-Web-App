// Anything the router does not recognise. (Phase 5)

import { Link } from 'react-router-dom';
import { EmptyState } from '../components/ui/States';
import { buttonClasses } from '../components/ui/buttonStyles';

export function NotFound() {
  return (
    <div className="mx-auto max-w-lg py-16">
      <EmptyState
        title="Page not found"
        description="That link does not lead anywhere in the clinic app."
        action={
          <Link to="/" className={buttonClasses('primary', 'md')}>
            Back to the dashboard
          </Link>
        }
      />
    </div>
  );
}
