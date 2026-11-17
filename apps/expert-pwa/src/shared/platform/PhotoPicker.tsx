import { useRef } from 'react';

import { CameraIcon, ImagesIcon } from '../ui/icons';

/**
 * Browser photo source (ARCHITECTURE.md §9). Two buttons backed by hidden file inputs:
 * the camera (`capture`, one photo per tap; iOS returns to the app after each shot) and the
 * photo library (multiple selection). Opening a picker must
 * happen directly in the tap handler, or iOS Safari ignores it; the inputs are visually
 * hidden rather than `display: none`, which some WebKit versions refuse to open. A native shell would
 * replace this component with camera/library plugins.
 *
 * Explicit types (rather than `image/*`) ask iOS to deliver HEIC originals instead of
 * converting them to JPEG; whether it does depends on the iOS version and settings and
 * must be verified on a device (docs/development.md).
 */
const LIBRARY_TYPES = 'image/jpeg,image/png,image/heic,image/heif';

export function PhotoPicker({
  onFiles,
  cameraLabel,
  libraryLabel,
  disabled,
}: {
  onFiles: (files: File[]) => void;
  cameraLabel: string;
  libraryLabel: string;
  disabled?: boolean;
}) {
  const camera = useRef<HTMLInputElement>(null);
  const library = useRef<HTMLInputElement>(null);

  const handle = (input: HTMLInputElement) => {
    const files = Array.from(input.files ?? []);
    input.value = ''; // allow choosing the same photo again
    if (files.length) onFiles(files);
  };

  return (
    <>
      <button
        type="button"
        className="button button--primary capture-button"
        disabled={disabled}
        onClick={() => camera.current?.click()}
      >
        <CameraIcon />
        <span>{cameraLabel}</span>
      </button>
      <button
        type="button"
        className="button capture-button"
        disabled={disabled}
        onClick={() => library.current?.click()}
      >
        <ImagesIcon />
        <span>{libraryLabel}</span>
      </button>
      <input
        ref={camera}
        type="file"
        accept="image/*"
        capture="environment"
        className="visually-hidden"
        tabIndex={-1}
        aria-label={cameraLabel}
        onChange={(event) => handle(event.currentTarget)}
      />
      <input
        ref={library}
        type="file"
        accept={LIBRARY_TYPES}
        multiple
        className="visually-hidden"
        tabIndex={-1}
        aria-label={libraryLabel}
        onChange={(event) => handle(event.currentTarget)}
      />
    </>
  );
}
