const TOAST_EVENT = "case-library:toast";

export function notify(message, type = "info") {
  window.dispatchEvent(
    new CustomEvent(TOAST_EVENT, {
      detail: {
        message,
        type,
      },
    })
  );
}

export { TOAST_EVENT };
