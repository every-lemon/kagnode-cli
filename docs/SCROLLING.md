# KagNode scrolling

Pages and overflow regions use the shared KagNode rails and real scroll positions. Wheel, touch, draggable thumbs and keyboard commands support nested regions and horizontal tables. Controls expose scrollbar roles and synchronized values. Reduced motion disables smoothing; pinch zoom is retained.

Choose **Use native scrolling** in the visible footer to restore the browser controls. This preference is stored locally when browser storage is available. Sandboxed fictional examples cannot share browser storage and keep their choice for that frame only. The native behavior remains the fallback if JavaScript does not initialize. Forced-color mode uses native controls.

Readable sources are `kagnode-scroll.js` and `kagnode-scroll.css` in the project's web/static/assets directory. Use the project's existing asset build after changes; production assets are minified and fingerprinted separately. Do not edit generated modules or hashed files.
