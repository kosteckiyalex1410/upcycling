import { backend } from './backend';

export default function globalSetup() {
  backend('python', '-m', 'scripts.ensure_database');
  backend('alembic', 'upgrade', 'head');
}
