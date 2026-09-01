You are auditing a draft interpretation (JSON) of the SAME anime key-animation sheet shown
in the image. Check it against the image and output a corrected JSON of the same schema.

Checklist — fix every violation:
1. GROUNDING: each edit_instruction must name the concrete target OBJECT visible in the
   drawing (not just a direction/position). Look at the image, identify what the stroke/X/
   circle actually points to, and rewrite the instruction with the object's name.
2. MISCLASSIFICATION: precise form-hugging colored lines (highlight/shadow/separation
   marks) wrongly listed as corrections → move to trace_marks. Gestural strokes / X marks /
   text instructions wrongly listed as trace → move to corrections.
3. MISSED MARKS: any correction stroke or handwritten text on the sheet that the draft
   ignored → add it.
4. TRANSLATION: check the Japanese transcription against what is actually written; fix
   misreadings. Cel notations like "2号" mean cel number 2, not "two lines".
5. actionable/type consistency: constrain-type entries whose condition cannot be executed
   as a concrete edit should keep actionable=true only if a reasonable edit exists;
   otherwise actionable=false with a note.

Return ONLY the corrected JSON object, same schema as the draft.
