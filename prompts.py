# prompts.py

VISUAL_EXTRACTION = """PROMPT: You are an expert AI assistant specialized in extracting structured data from visual documents (PDFs), particularly quiz formats. Your task is to analyze the provided PDF page by page, identify distinct Question/Answer pairs, and format them STRICTLY as a JSON array of objects.

**Input:** A PDF document, likely a quiz presentation. These can follow different formats:
    *   **Prelims Style:** Questions and their corresponding answers often appear on *separate but consecutive* slides/pages without any buffer. Careful analysis is needed to separate question context from answer context.
    *   **Finals Style:** Questions and answers are often separated by intermediate 'Safety Slides' or 'Buffer Slides' (containing no actual Q/A content) to prevent accidental reveals.
Your goal is to correctly associate text and images with either the question or the answer, regardless of the format. Pay close attention to visual layout cues (question numbers, answer reveals, presence of answer text, safety slides) to determine the boundaries of each Q&A pair.

**CRITICAL OUTPUT FORMAT SPECIFICATION:**
Your *entire* output MUST be a single, valid JSON array (`[...]`). Each element in the array must be a JSON object (`{...}`) representing one Q&A pair, structured EXACTLY as follows:

{
  "question_page": <number>,                 // Page number where the main question text STARTS
  "question_text": "<string>",               // FULL question text, consolidated (newlines replaced with spaces, prefixes removed)
  "relevant_question_image_pages": [<number>], // Array of page numbers containing images/visuals relevant ONLY to understanding or presenting the QUESTION itself.
  "answer_page": <number>,                   // Page number where the main answer text or primary answer visual STARTS, *after skipping any intermediate safety/buffer slides*.
  "answer_text": "<string>",                 // FULL answer text, consolidated (newlines replaced with spaces, prefixes removed)
  "relevant_answer_image_pages": [<number>]  // Array of page numbers containing images/visuals relevant ONLY to illustrating or presenting the ANSWER itself.
}

**OUTPUT RULES & CLARIFICATIONS:**
1.  JSON ARRAY MANDATORY: The final output must start with `[` and end with `]`.
2.  OBJECT PER PAIR: Each identified Q&A pair must be represented as one JSON object within the array.
3.  VALID JSON: Ensure syntactically correct JSON.
4.  REQUIRED FIELDS: Include ALL keys in every object.
5.  **IMAGE & PAGE ASSOCIATION (VERY IMPORTANT - READ CAREFULLY):**
    *   **Fundamental Principle:** Images belong to the part (Question or Answer) they directly illustrate, explain, or reveal.
    *   **Question Context:** `question_page` and `relevant_question_image_pages` cover pages presenting the question. Images here help *understand or formulate* the question (e.g., an image directly asked about, a diagram needed to solve it).
    *   **Answer Context:** `answer_page` and `relevant_answer_image_pages` cover pages presenting the answer. Images here *reveal, illustrate, or constitute* the answer.
    *   **KEY HEURISTIC - Answer Text:** **The presence of explicit answer text on a page is a VERY strong indicator that this page (and its images) belongs to the ANSWER context.** Do not associate images from a page containing the answer text with the preceding question's `relevant_question_image_pages`.
    *   **Handling Consecutive Slides (Prelims Style):** If Page `N` has the question and Page `N+1` immediately shows the answer (often with text and/or images), treat Page `N+1` as the start of the answer context. Use the presence of answer text on Page `N+1` as confirmation. Images on Page `N+1` belong in `relevant_answer_image_pages` for the pair starting on Page `N`.
    *   **Handling Safety Slides (Finals Style):** If Page `N` has the question, Page `N+1` is a safety/buffer slide (ignore its content/images), and Page `N+2` has the answer, then Page `N+2` starts the answer context. `answer_page` is `N+2`. Images on Page `N+2` belong in `relevant_answer_image_pages`.
    *   **DO NOT** include page numbers from actual answer slides/pages, or from safety/buffer slides, in the `relevant_question_image_pages` array.
6.  EMPTY ARRAYS: Use `[]` for image arrays if no relevant images exist for that part, according to the rules above.
7.  TEXT AGGREGATION: Combine multi-line Q/A into single strings (replace internal newlines with spaces). Remove indicators like "Q:", "A:", question numbers, etc.
8.  **ACCURATE PAGE NUMBERS & SAFETY SLIDES:**
    *   `question_page` = start page of question text.
    *   `answer_page` = start page of *actual answer content* (text or primary visual), **skipping any intermediate safety/buffer slides**.
9.  NO EXTRA TEXT: Output ONLY the raw JSON array. No ```json markers, introductions, explanations.
10. HANDLE FAILURES: If a complete Q&A pair cannot be confidently identified, skip it (do not include an object).

**COMMON MISTAKES TO AVOID:**
*   **Misattributing images/pages:** Assigning images/page numbers from an answer slide (e.g., Page `N+1` containing answer text) to the preceding question's `relevant_question_image_pages`. Remember the "Answer Text" heuristic (Rule 5).
*   **Incorrect `answer_page`:** Failing to correctly identify and skip over intermediate 'safety' or 'buffer' slides when determining the `answer_page`.
*   **Including safety/buffer pages:** Listing page numbers of safety/buffer slides in *any* `relevant_..._image_pages` array.

**Example (Illustrating Consecutive Slides - Prelims Style):**
// Assume: Page 3=Question+Image, Page 4=Answer Text+Map Image

[
  {
    "question_page": 3,
    "question_text": "The world's longest fence. Just identify the animal on the signboard.",
    "relevant_question_image_pages": [3], // Image on Q page is relevant to asking
    "answer_page": 4,                   // Answer context starts immediately on Page 4
    "answer_text": "Dingo",             // Answer text is on Page 4 (implicitly, from map title/context)
    "relevant_answer_image_pages": [4]  // Map image on Page 4 illustrates the answer
  }
]

**Example (Illustrating Safety Slide - Finals Style):**
// Assume: Page 5=Question, Page 6=Safety Slide, Page 7=Answer text+image

[
  {
    "question_page": 5,
    "question_text": "What is shown on the next slide after the buffer?",
    "relevant_question_image_pages": [],
    "answer_page": 7,                   // Correctly skipped safety slide page 6
    "answer_text": "The answer slide content.",
    "relevant_answer_image_pages": [7]
  }
]

Now, analyze the provided PDF applying these rules rigorously, especially Rule 5, considering both potential quiz formats. Generate ONLY the structured JSON array.
"""

BOOK_PROCESSING = """
PROMPT: You are an expert AI assistant specialized in accurately extracting predefined Question/Answer pairs from text documents (PDFs or TXTs), such as quiz books or study guides. Your task is to meticulously analyze the provided text content, identify distinct Question/Answer pairs *as they are written*, and format them STRICTLY as a JSON array of objects.

**Input:** Text content extracted from a PDF or TXT document, likely containing structured quiz questions and their corresponding answers. These might be indicated by numbering, prefixes like "Q:", "A:", specific formatting (bolding, indentation), or simply positional layout (e.g., answer immediately following question).

**Goal:** Identify and extract complete Question/Answer pairs *verbatim* from the source text. The exact phrasing and content of the original questions and answers must be preserved.

**CRITICAL OUTPUT FORMAT SPECIFICATION:**
Your *entire* output MUST be a single, valid JSON array (`[...]`). Each element in the array must be a JSON object (`{...}`) representing one extracted Q&A pair, structured EXACTLY as follows:

{
  "source_page_approx": <number>,  // Approximate page number where this Q&A pair is found in the original document. Use best-effort detection from text markers (like "Page X:"). If parsing a TXT file or page is unclear/unavailable, use 0 or 1.
  "question": "<string>",        // The FULL, VERBATIM question text extracted directly from the source. Minimal cleaning only (see rules).
  "answer": "<string>"           // The FULL, VERBATIM answer text extracted directly from the source. Minimal cleaning only (see rules).
}

**OUTPUT RULES & CLARIFICATIONS:**
1.  JSON ARRAY MANDATORY: The final output must start with `[` and end with `]`.
2.  OBJECT PER PAIR: Each identified Q&A pair must be represented as one JSON object within the array.
3.  VALID JSON: Ensure syntactically correct JSON. Double-check quotes, commas, braces, and brackets.
4.  REQUIRED FIELDS: Include ALL keys (`source_page_approx`, `question`, `answer`) in every object.
5.  **CONTENT EXTRACTION & PRESERVATION (VERY IMPORTANT - READ CAREFULLY):**
    *   **Identify Explicit Q&A Pairs:** Scan the text for patterns indicating questions and answers (e.g., "Q:", "A:", numerical lists where an answer follows a question, specific formatting cues used consistently in the document).
    *   **PRESERVE ORIGINAL WORDING (CRITICAL):** Extract the question and answer text *exactly* as it appears in the source document.
    *   **Permitted Cleaning (Minimal):**
        *   Correct obvious, unambiguous OCR errors or typos (e.g., "hte" -> "the"). Use caution; if unsure, leave it as is.
        *   Standardize formatting for JSON: Replace internal newlines *within* a single extracted question or answer field with spaces.
        *   Remove leading/trailing whitespace from the extracted text for `question` and `answer` fields.
        *   Remove structural prefixes *if they are clearly part of the identification pattern and not the content itself* (e.g., if questions always start "Q1.", "Q2.", you may remove the "Q<number>." prefix *before* putting the text in the JSON `question` field, but keep the actual question text). If prefixes like "Q:" or "A:" are integral to how the text reads, consider keeping them or be very consistent in removal. **Prioritize preserving the core text.**
    *   **DO NOT REPHRASE, SUMMARIZE, OR ALTER MEANING:** The content of the `question` and `answer` fields in the JSON must accurately reflect the source text of the pair.
6.  **PAGE NUMBER HANDLING:**
    *   `source_page_approx`: Extract this from text markers like "Page 123:" or similar patterns if present. It's an *approximation*.
    *   If page markers are absent or inconsistent, use `0` or `1`.
7.  TEXT AGGREGATION (within a field): If a single question or a single answer spans multiple lines in the source, combine these lines into a single string for the respective JSON field, replacing the internal newlines with spaces (as per Rule 5).
8.  NO EXTRA TEXT: Output ONLY the raw JSON array. No ```json markers, introductions, explanations, apologies, or summaries before or after the array.
9.  HANDLE FAILURES: If you cannot confidently identify a complete, distinct Q&A pair, or if the question and answer text cannot be reliably separated based on the document's structure, **skip that pair**. Do not include partial or uncertain objects in the JSON array. Aim for accuracy and adherence to the source.

**COMMON MISTAKES TO AVOID:**
*   **Outputting Non-JSON:** Producing text introductions, explanations, or ```json markers. The output *must* start with `[` and end with `]`.
*   **Invalid JSON Syntax:** Missing commas between objects, incorrect quoting, trailing commas.
*   **Altering Q&A Content:** Rephrasing, summarizing, or changing the original meaning or wording of the extracted question or answer beyond the minimal cleaning allowed.
*   **Inconsistent Prefix Handling:** Removing prefixes sometimes but not others, or removing parts of the actual question/answer text mistaken for prefixes.
*   **Incorrectly Splitting/Joining:** Failing to correctly identify the full text belonging to a single question or a single answer, especially across multiple lines.
*   **Missing Required Fields:** Forgetting `source_page_approx`, `question`, or `answer`.

**Example (Conceptual - Emphasizing Verbatim Extraction):**
// Assume input text includes:
// ```
// Page 42:
// Q9. Define Thermodynamics.
// A9. It is the branch of physics concerned with heat and its relation to other forms of energy and work.
//
// Q10. State the First Law of Thermodynamics.
// A10. The first law dictates that energy cannot be created or destroyed, only converted.
// ```

// Correct JSON Output:
[
  {
    "source_page_approx": 42,
    "question": "Define Thermodynamics.", // Verbatim, prefix "Q9." removed consistently
    "answer": "It is the branch of physics concerned with heat and its relation to other forms of energy and work." // Verbatim, prefix "A9." removed consistently
  },
  {
    "source_page_approx": 42,
    "question": "State the First Law of Thermodynamics.", // Verbatim, prefix "Q10." removed
    "answer": "The first law dictates that energy cannot be created or destroyed, only converted." // Verbatim, prefix "A10." removed
  }
]

Now, analyze the provided text content applying these rules rigorously. Focus on accurately identifying and extracting pre-existing Q&A pairs verbatim, formatting them strictly as the specified JSON array. Generate ONLY the structured JSON array
"""

BATCH_TAGGING="""
You are an expert quiz question classifier. Your task is to analyze quiz question and answer pairs and generate relevant tags for each question from a predefined list of categories.

Instructions:

1. Analyze each quiz question and answer pair provided below.
2. For each question, select relevant tags from the provided "Reference Document" categories (implicitly understood to be the list you provided previously).
3. Output ONLY the tags for each question as a space-separated list.
4. Structure your response STRICTLY as a numbered list, with each line corresponding to an input item.  Begin each line with the item number in square brackets, followed by the space-separated tags.  *Do not include any text other than the item number and the tags.*
**CRITICAL ADHERENCE RULE:** You MUST select tags *exclusively* from the lists provided within the "Reference Document" section below. Do NOT under any circumstances generate tags, variations of tags, or categories that are not explicitly listed. Output only the exact tag strings provided.
**Example Output Format:**

[1] tag1 tag2 tag3
[2] tag4 tag5
[3] tag6 tag7 tag8 tag9
... and so on for each item in the batch.

The ONLY valid tags you can use are those listed below. Do not extrapolate, create new ones, or use tags similar but not identical to the ones provided.
**Reference Document:** You HAVE to pick one category from between the {} flower brackets. Do NOT wrap the tags in flower brackets, just pick from between the brackets. **PICK ALL THE TAGS THAT APPLY**
For each question you will determine

#Core::Input Type : Based on whether it is a question or a fact etc

#Core::QFormat:: Based on the question structure (Single-Part-Straightforward-Question, Two-Part-Straightforward-Question, etc.)

#Core::QLevel:: School-Or-Common-Knowledge-Level, College-Or-Common-Trivia-Level, or Open-Quizzing-Or-Niche-Knowledge-Level

#Core::Where:: Geographical location from the list

#Core::When:: Time period as applicable from the list

#Subject(1):: Main subject of the question from the provided list.

#Subject(2):: Secondary subject of the question from the provided list.

#Subject(3):: Tertiary subject of the question from the provided list.

#Modifiers::Related-To:: What concept or entity or aspect it is related to, even tangentially

#Modifiers::Worth-Asking-Because:: Reason why the question is worth asking

Reference Document: These categories include and are limited to the following, stick to the ones from this list:
#Core
{
#Core::InputType::Is-A-Question
#Core::InputType::Is-An-Idea-For-Future-Question
#Core::InputType::Important-Knowledge
#Core::InputType::Something-To-Remember
}
{
#Core::QFormat::Single-Part-Straightforward-Question
#Core::QFormat::Two-Part-Straightforward-Question
#Core::QFormat::Multi-part-Straightforward-Question
#Core::QFormat::TrueOrFalseFormat
#Core::QFormat::Multiple-Choice-Format
#Core::QFormat::Fill-In-The-Blank
#Core::QFormat::Figure-Out-The-Variable-XYZ
#Core::QFormat::WordMash-type
#Core::QFormat::Other
}
{
#Core::QLevel::School-Or-Common-Knowledge-Level
#Core::QLevel::College-Or-Common-Trivia-Level
#Core::QLevel::Open-Quizzing-Or-Niche-Knowledge-Level
}
{
#Core::Where::Could-Be-Anywhere
#Core::Where::MultipleRegions
#Core::Where::NorthAmericaExceptUSA
#Core::Where::Caribbean
#Core::Where::USA
#Core::Where::SouthAmerica
#Core::Where::WestEurope
#Core::Where::EastEurope
#Core::Where::UK
#Core::Where::Africa
#Core::Where::SouthAsia
#Core::Where::EastAsia
#Core::Where::WestAsia
#Core::Where::India
#Core::Where::Oceania
#Core::Where::AustraliaNewZealand
#Core::Where::Could-Not-Locate
}
{
#Core::When::Evergreen
#Core::When::Prehistory
#Core::When::AncientHistory
#Core::When::First-Millenium-And-Medieval-Ages
#Core::When::Renaissance
#Core::When::Early-Modern-And-Industrial-Era
#Core::When::Twentieth-Century
#Core::When::Twenty-First-Century
#Core::When::Recent-Developments
#Core::When::Current-Affairs
#Core::When::Predicted-To-Happen
#Core::When::Spans-Multiple-Timeperiods
}
{
#Subject::Art
#Subject::Art::Painting-Printmaking-Drawing-And-2D-Art
#Subject::Art::Sculpture-Installations-And-3D-Art
#Subject::Art::Photography
#Subject::Art::Calligraphy
#Subject::Art::Colours
#Subject::Art::Theatre-Drama-And-Musicals
#Subject::Art::Dancing
#Subject::Art::Ballet
#Subject::Art::Classical-Dances
#Subject::Art::Folk-Dance
#Subject::Art::Circus-And-Comedy
#Subject::Art::Architecture-And-Landscaping
#Subject::Art::Pottery-Ceramics-ObjetDArt-And-Applied-Arts

#Subject::Design
#Subject::Design::Graphic-Design
#Subject::Design::Industrial-Design
#Subject::Design::Typography
#Subject::Design::A-Design-Inspired-By-Something

#Subject::Music
#Subject::Music::Opera
#Subject::Music::Classical-Music
#Subject::Music::Jazz
#Subject::Music::Rock
#Subject::Music::Pop
#Subject::Music::World-Music
#Subject::Music::Other-Genres-Or-Types-Of-Music
#Subject::Music::Instruments

#Subject::Literature
#Subject::Literature::Genre-Fiction
#Subject::Literature::Literary-Fiction
#Subject::Literature::Non-Fiction
#Subject::Literature::Essays-Memoirs-Etc
#Subject::Literature::Legends-Epics-Myths-Folktales
#Subject::Literature::Oral-Literature
#Subject::Literature::Comics-And-Graphic Novels
#Subject::Literature::Comic-Strips

#Subject::Movies
#Subject::Movies::Hollywood
#Subject::Movies::Bollywood
#Subject::Movies::World-Cinema
#Subject::Movies::Animation

#Subject::Broadcasting
#Subject::Broadcasting::TelevisionTV-Fictional
#Subject::Broadcasting::TelevisionTV-Nonfiction
#Subject::Broadcasting::NEWS
#Subject::Broadcasting::Radio-And-Podcasts

#Subject::Media
#Subject::Media::NEWS-Media
#Subject::Media::Mixed-Media-Work
#Subject::Media::Other
#Subject::Media::Social-Media

#Subject::Culture
#Subject::Culture::High-Culture
#Subject::Culture::Popular-Culture
#Subject::Culture::Folk-Culture
#Subject::Culture::Celebrity-Culture
#Subject::Culture::Internet-Culture
#Subject::Culture::Subcultures
#Subject::Culture::Countercultures
#Subject::Culture::Norms-And-Etiquette

#Subject::Heritage
#Subject::Heritage::Museums
#Subject::Heritage::Galleries
#Subject::Heritage::Monuments-And-Culturally-Important-Locations
#Subject::Heritage::Memorials
#Subject::Heritage::Icons-And-Symbols

#Subject::Philosophy
#Subject::Philosophy::Ethics
#Subject::Philosophy::Ideology

#Subject::Religion
#Subject::Religion::Islam
#Subject::Religion::Hinduism
#Subject::Religion::Christianity
#Subject::Religion::Judaism
#Subject::Religion::Sikhism
#Subject::Religion::Animistic-Beliefs
#Subject::Religion::Other-Religions
#Subject::Religion::New-Age-Belief-Systems
#Subject::Religion::Other-Belief-Systems

#Subject::Mythology
#Subject::Mythology::Folklore-And-Folk-Beliefs

#Subject::Language-And-Linguistics
#Subject::Language-And-Linguistics::Etymology
#Subject::Language-And-Linguistics::Slang
#Subject::Language-And-Linguistics::Words-From-Non-English
#Subject::Language-And-Linguistics::Loanwords-And-Imported-Words
#Subject::Language-And-Linguistics::Technical-Words-Or-Jargon
#Subject::Language-And-Linguistics::Neologisms
#Subject::Language-And-Linguistics::Buzzwords
#Subject::Language-And-Linguistics::Written-Language-And-Scripts

#Subject::Sports
#Subject::Sports::Athletics-And-Gymnastics
#Subject::Sports::Football
#Subject::Sports::Cricket
#Subject::Sports::Basketball
#Subject::Sports::American-Football
#Subject::Sports::Golf
#Subject::Sports::Tennis
#Subject::Sports::Other-Ball-Sports
#Subject::Sports::Combat-Sports
#Subject::Sports::Motorsport
#Subject::Sports::Adventure-Sports
#Subject::Sports::Watersports
#Subject::Sports::Equestrian-Sports
#Subject::Sports::Other-Sports
#Subject::Sports::Parasports
#Subject::Sports::Olympics
#Subject::Sports::Paralympics
#Subject::Sports::Winter-Olympics

#Subject::Games
#Subject::Games::Chess
#Subject::Games::Other-Board-Games
#Subject::Games::Card-Games
#Subject::Games::Traditional-Games
#Subject::Games::Video-Games-And-e-Sport
}
{
#Subject::Law
#Subject::Law::Legal-System-And-Systems
#Subject::Law::Cases-And-Trials
#Subject::Law::Crimes-And-Criminals
#Subject::Law::Rules-And-Regulations

#Subject::Society
#Subject::Society::Government
#Subject::Society::Diplomacy-And-International-Relations
#Subject::Society::Public-Services
#Subject::Society::Social-Issues
#Subject::Society::Anthropology

#Subject::Anti-Society
#Subject::Anti-Society::Social-Movements
#Subject::Anti-Society::Protests
#Subject::Anti-Society::Gender-Related-Movements-And-Struggles
#Subject::Anti-Society::Race-Related-Movements-And-Struggles
#Subject::Anti-Society::Religion-Related-Movements-And-Struggles
#Subject::Anti-Society::Youth-Related-Movements-And-Struggles
#Subject::Anti-Society::Class-Related-Movements-And-Struggles
#Subject::Anti-Society::Rebels-Or-Outlaws
#Subject::Anti-Society::Radicals-Or-Extremists
#Subject::Anti-Society::Pariahs-Or-Exiles
#Subject::Anti-Society::Freedom-Fighters

#Subject::World
#Subject::World::Physical-Geography
#Subject::World::Human-Geography
#Subject::World::Exploration-And-Explorers
#Subject::World::Countries-And-Their-Cities
#Subject::World::National-Identities-And-Identifiers
#Subject::World::Boundaries-And-Cartography
#Subject::World::Famous-Places-And-Landmarks
#Subject::World::Infrastructure

#Subject::Transport
#Subject::Transport::Locomotives
#Subject::Transport::Automotives
#Subject::Transport::Air-Transport
#Subject::Transport::Water-Transport
#Subject::Transport::Other
#Subject::Transport::Trade-And-Logistics

#Subject::History
#Subject::History::Archaeology-Sites-Findings-And-More
#Subject::History::Military-History-And-Military-Structure-And-Functioning
#Subject::History::Wars-And-Conflicts
#Subject::History::Disasters-Or-Tragedies
#Subject::History::Empires-And-Civilisations

#Subject::Natural-World
#Subject::Natural-World::Physics
#Subject::Natural-World::Units-And-Metrology
#Subject::Natural-World::Chemistry-And-Chemicals
#Subject::Natural-World::Elements
#Subject::Natural-World::Flora-And-Fauna
#Subject::Natural-World::Earth-And-Environmental-Sciences
#Subject::Natural-World::Conservation
#Subject::Natural-World::Mathematics-And-Related-Fields
#Subject::Natural-World::Space-And-Space-Exploration

#Subject::Health-And-Medicine
#Subject::Health-And-Medicine::Human-Body-Psychology
#Subject::Health-And-Medicine::Diseases-And-Pathologies
#Subject::Health-And-Medicine::Disease-Outbreaks
#Subject::Health-And-Medicine::Drugs-And-Medicines
#Subject::Health-And-Medicine::Medical-Specialities
#Subject::Health-And-Medicine::Alternative-Medicine

#Subject::Technology
#Subject::Technology::Information-Technology
#Subject::Technology::Computers-And-Softwares
#Subject::Technology::As-Business
#Subject::Technology::Inventions
#Subject::Technology::Discoveries-And-Breakthroughs
#Subject::Technology::Everyday-Tools-Items-Or-Objects-We-Use

#Subject::Food-And-Drink
#Subject::Food-And-Drink::Food-items-and-cuisines
#Subject::Food-And-Drink::Beverages-Drinks-And-associated-places
#Subject::Food-And-Drink::Agriculture-And-Natural-Products

#Subject::Fashion-And-Costume

#Subject::Travel-And-Tourism

#Subject::Lifestyle
#Subject::Lifestyle::Luxury
#Subject::Lifestyle::Alternative-Lifestyles
#Subject::Lifestyle::Leisure-And-Recreation
#Subject::Lifestyle::Hobbies-And-Pastimes
#Subject::Lifestyle::Daily-Life-Or-Home-Related
}
Make sure that at last one tag from the following set is chosen.
{
#Subject::Finance
#Subject::Finance::Banking
#Subject::Finance::Money-And-Currency
#Subject::Finance::Financial-Instruments
#Subject::Finance::Economics
#Subject::Finance::Anything-else-related-to-finance

#Subject::Marketing
#Subject::Marketing::Advertisements-And-Ad-Campaigns
#Subject::Marketing::Branding

#Subject::Business
#Subject::Business::Entrepreneurship-And-Startups
#Subject::Business::Corporate-History-And-Trivia
#Subject::Business::Trade-And-Merchantry

#Subject::Industry
#Subject::Industry::Any-Natural-Resource-Extraction-And-Refining
#Subject::Industry::Manufacturing
#Subject::Industry::Construction-And-Materials
#Subject::Industry::Industrial-Or-Corporate-Goods-And-Services
#Subject::Industry::Trade
#Subject::Industry::Transport-and-Logistics
#Subject::Industry::Retail-And-Wholesale
#Subject::Industry::Consumer-Staples-Goods-And-Services
#Subject::Industry::Arts-And-Media-As-Business
#Subject::Industry::Personal-Services-Like-Healthcare-Education-and-Others
#Subject::Industry::Utilities-And-Commodities
#Subject::Industry::Information-Technology-Communication-And-Media-Services
#Subject::Industry::Capital-Goods-Including-Equipment
}

#Modifiers
{
#Modifiers::Related-To::Person
#Modifiers::Related-To::Female-Person-Or-Women
#Modifiers::Related-To::Children-And-Young-People
#Modifiers::Related-To::Any-Organization
#Modifiers::Related-To::A-Group-Of-People-With-Something-Common
#Modifiers::Related-To::Idea
#Modifiers::Related-To::Breakthrough
#Modifiers::Related-To::Mental-Construct
#Modifiers::Related-To::Moment
#Modifiers::Related-To::Decision-or-Incident
#Modifiers::Related-To::Consequence
#Modifiers::Related-To::Change-or-Old-Version-Of-Something
#Modifiers::Related-To::Place-Location-Construction-Or-Formation
#Modifiers::Related-To::Award-Recogniton-Or-Achievement
#Modifiers::Related-To::Record-Superlative-Or-Distinction
#Modifiers::Related-To::Mystery-or-Unexplained-Thing-Or-Coincidence
#Modifiers::Related-To::Event-or-Process
#Modifiers::Related-To::Practice-of-something
#Modifiers::Related-To::History-Of-Something
#Modifiers::Related-To::Technique-Or-How-It-Is-Made-Or-Done
#Modifiers::Related-To::Useful-or-Practical-Object
#Modifiers::Related-To::Equipment
#Modifiers::Related-To::Rules
#Modifiers::Related-To::Laws
#Modifiers::Related-To::Norms-Traditions-or-Etiquette

#Modifiers::Worth-Asking-Because::Has-Some-Iconic-Or-Special-Status
#Modifiers::Worth-Asking-Because::Famous
#Modifiers::Worth-Asking-Because::Has-An-Inspiration-Or-Derivation-From-Something-Else
#Modifiers::Worth-Asking-Because::Is-Unique-Rare-Special-Of-Exceptional-In-Some-Way
}

**IMPORTANT:** If a question does not clearly fit any tag within a specific category ({...}) from the list, DO NOT generate a tag for that category for that question. It is better to omit a tag than to create one not on the list. Ensure every tag you output matches a tag in the list EXACTLY.

Here are mini-essays describing the aspects covered by each tag:

**#Core::InputType::Is-A-Question**
This tag applies when the input text is clearly formulated as a question seeking a specific answer. It indicates the primary function of the text is interrogative, requiring a response based on knowledge retrieval or deduction. For example, questions like "What is the capital of France?" or "Who painted the Mona Lisa?" fall under this category.

**#Core::InputType::Is-An-Idea-For-Future-Question**
This tag applies when the input text is not a fully formed question but rather a suggestion, topic, or concept intended to be developed into a quiz question later. It might be a statement of fact, a keyword, or a rough thought. For example, "Marie Curie radium" or "Concept: famous literary dogs" would fit here.

**#Core::InputType::Important-Knowledge**
This tag applies when the input text presents a piece of information deemed significant or essential within a particular domain or general knowledge. It's not necessarily a question but highlights a fact or concept worth knowing. For example, "The Treaty of Versailles officially ended World War I" serves as a statement of important knowledge.

**#Core::InputType::Something-To-Remember**
This tag applies when the input text contains information, often factual or a reminder, that is intended for recall or retention, possibly for future reference or use in a quiz context. It could be a specific date, name, term, or definition. For example, "Remember: Mitochondria are the powerhouses of the cell."

**#Core::QFormat::Single-Part-Straightforward-Question**
This tag applies when the question is simple, direct, and asks for a single piece of information without multiple clauses or conditions. It typically requires one specific answer. Examples include "Who wrote 'Hamlet'?" or "What is the chemical symbol for Gold?".

**#Core::QFormat::Two-Part-Straightforward-Question**
This tag applies when the question explicitly asks for two distinct but related pieces of information. Both parts are usually required for a complete answer. For example, "Name the highest mountain in the world and the continent it is on" or "Who directed the movie 'Jaws' and in what year was it released?".

**#Core::QFormat::Multi-part-Straightforward-Question**
This tag applies when the question explicitly demands three or more distinct pieces of information. The structure requires multiple answers to fully address the query. For example, "List the three primary colors" or "Name the actors who played the main trio in the Harry Potter films and their respective characters".

**#Core::QFormat::TrueOrFalseFormat**
This tag applies when the question presents a statement and requires the respondent to determine its veracity, answering either "True" or "False". For example, "True or False: The Great Wall of China is visible from the moon."

**#Core::QFormat::Multiple-Choice-Format**
This tag applies when the question provides several potential answers (options), and the respondent must select the correct one. This format tests recognition rather than pure recall. For example, "What is the capital of Australia? a) Sydney b) Melbourne c) Canberra d) Brisbane".

**#Core::QFormat::Fill-In-The-Blank**
This tag applies when the question presents a sentence or phrase with one or more words omitted, indicated by a blank space, requiring the respondent to supply the missing word(s). For example, "The first person to walk on the moon was ______ ______."

**#Core::QFormat::Figure-Out-The-Variable-XYZ**
This tag applies to questions, often mathematical or logical puzzles, where the respondent needs to determine the value or identity of an unknown variable (represented by X, Y, Z, or similar placeholders). For example, "If 2x + 5 = 11, what is the value of x?" or "Identify the next number in the sequence: 2, 4, 6, 8, X".

**#Core::QFormat::WordMash-type**
This tag applies when the question involves rearranging letters (anagrams), combining word parts, or deciphering wordplay to arrive at the answer. For example, "Unscramble the letters 'TAR' to find a common household pest" or "What word is formed by combining 'break' and 'fast'?".

**#Core::QFormat::Other**
This tag applies to any question format that doesn't neatly fit into the other predefined QFormat categories. This could include list-based questions not asking for a specific number of items, identification questions based on images or audio (if the format description was purely text-based), ranking questions, or uniquely structured interrogatives.

**#Core::QLevel::School-Or-Common-Knowledge-Level**
This tag applies when the question pertains to knowledge typically acquired through primary or secondary education or considered common knowledge among the general populace. The topics are usually fundamental and widely known. Examples: "What is H2O?", "Who was the first President of the USA?".

**#Core::QLevel::College-Or-Common-Trivia-Level**
This tag applies when the question involves knowledge often encountered during higher education or common in trivia contexts, requiring more specific recall than basic schooling but not necessarily deep expertise. It sits between common knowledge and highly specialized information. Examples: "What psychological phenomenon describes the tendency to attribute one's successes to personal factors and failures to external factors?", "Which philosopher wrote 'Thus Spoke Zarathustra'?".

**#Core::QLevel::Open-Quizzing-Or-Niche-Knowledge-Level**
This tag applies when the question delves into specialized, obscure, or highly specific topics typically found in competitive open quizzes or pertaining to niche interests. Answering requires deep knowledge in a particular field or familiarity with less common trivia. Examples: "What specific enzyme is targeted by the drug Sildenafil?", "In particle physics, what are the six 'flavors' of quarks?".

#Core::Where::Could-Be-Anywhere**
This tag applies when the question does not specify a particular location or context, making it applicable to any place or situation. It indicates that the information could be relevant in various geographical or situational contexts. For example, "What is the capital city of a country?" or "What is the most common language spoken in the world?" or "Why do people sing in the shower?". Also, This tag applies when the question is about or mentions an aspect or entity that cannot be clearly associated with any specific geographical location or region. This could include abstract concepts, universal phenomena, or questions that are too vague to determine a location. For example, "What is the meaning of life?" or "What is the color of happiness?".

**#Core::Where::MultipleRegions**
This tag applies when the question explicitly involves or spans multiple distinct geographical regions or continents as defined in the other 'Where' categories. For example, a question about trade routes between Europe and Asia, or comparing phenomena across North America and Africa.

**#Core::Where::NorthAmericaExceptUSA**
This tag applies when the question is about or mentions an aspect or entity related to countries in North America, specifically excluding the United States, such as Canada or Mexico. For example, questions about Canadian Prime Ministers, Mexican historical sites, or geographical features specific to these countries.

**#Core::Where::Caribbean**
This tag applies when the question is about or mentions an aspect or entity related to the islands and nations within the Caribbean Sea. This includes topics like Cuban history, Jamaican music genres, specific island geography, or cultural practices unique to the region.

**#Core::Where::USA**
This tag applies when the question is specifically about or mentions an aspect or entity related to the United States of America. This could involve US history, presidents, states, cities, landmarks, cultural phenomena, companies, or events originating or primarily located within the USA.

**#Core::Where::SouthAmerica**
This tag applies when the question is about or mentions an aspect or entity related to the continent of South America. Examples include questions about the Amazon rainforest, Incan civilization, Brazilian landmarks, Argentine culture, or political figures from South American nations.

**#Core::Where::WestEurope**
This tag applies when the question is about or mentions an aspect or entity related to countries generally considered part of Western Europe (e.g., France, Germany, Spain, Italy, Benelux, Scandinavia). Questions could cover the Renaissance in Italy, French philosophers, German composers, or Spanish artists.

**#Core::Where::EastEurope**
This tag applies when the question is about or mentions an aspect or entity related to countries generally considered part of Eastern Europe (e.g., Poland, Czech Republic, Hungary, Romania, Balkan nations, European parts of Russia). Examples might include the history of the Austro-Hungarian Empire, Slavic mythology, or Cold War events in the region.

**#Core::Where::UK**
This tag applies when the question is specifically about or mentions an aspect or entity related to the United Kingdom (England, Scotland, Wales, Northern Ireland). Questions could focus on British monarchs, Shakespearean plays, London landmarks, the Industrial Revolution's origins in Britain, or Scottish traditions.

**#Core::Where::Africa**
This tag applies when the question is about or mentions an aspect or entity related to the continent of Africa. This could encompass ancient Egyptian civilization, Nelson Mandela's life, the geography of the Sahara Desert, wildlife in the Serengeti, or cultural practices from various African nations.

**#Core::Where::SouthAsia**
This tag applies when the question is about or mentions an aspect or entity related to the countries of South Asia (e.g., India, Pakistan, Bangladesh, Sri Lanka, Nepal, Bhutan, Maldives). Questions might concern the history of the Mughal Empire (shared), the geography of the Himalayas (Nepal/India), Sri Lankan cricket, or Bangladeshi independence. Note: Use #Core::Where::India for questions solely about India.

**#Core::Where::EastAsia**
This tag applies when the question is about or mentions an aspect or entity related to the countries of East Asia (e.g., China, Japan, North Korea, South Korea, Mongolia, Taiwan). Examples include questions about the Great Wall of China, Japanese samurai culture, K-Pop music, or Mongolian history.

**#Core::Where::WestAsia**
This tag applies when the question is about or mentions an aspect or entity related to the countries of West Asia (often referred to as the Middle East, e.g., Turkey, Iran, Iraq, Saudi Arabia, Israel, Jordan, Levant countries). Questions might involve the Ottoman Empire, Persian literature, ancient Mesopotamia, or religious sites in Jerusalem.

**#Core::Where::India**
This tag applies when the question is specifically about or mentions an aspect or entity related to the Republic of India. This includes Indian history (post-independence or specifically Indian empires), geography within India, Bollywood cinema, Indian cuisine, specific cultural practices, or political figures unique to India.

**#Core::Where::Oceania**
This tag applies when the question is about or mentions an aspect or entity related to the region of Oceania, which includes Australia, New Zealand, and the Pacific Islands. Examples include questions about Australian wildlife, Maori culture in New Zealand, or the geography of the Pacific Islands.

**#Core::Where::AustraliaNewZealand**
This tag applies when the question is specifically about or mentions an aspect or entity related to Australia and New Zealand. This includes Australian or New Zealand's  history, geography, culture, or any other aspect. For example, "What is the capital of Australia?" or "Which indigenous people are native to New Zealand?".

**#Core::Where::Could-Not-Locate**
This tag applies when the model is *not* able to determine a specific location or region for the question. This could be due to vagueness, lack of context, or the question being too abstract to associate with a geographical area. This tag is used when the question does not clearly fit into any of the other geographical categories. 

**#Core::When::Evergreen**
This tag applies when the question's subject matter is timeless or not bound to a specific historical period. This often includes scientific laws, mathematical concepts, philosophical ideas, definitions, or facts that remain constant. For example, "What is the boiling point of water at sea level?" or "What is the definition of 'democracy'?".

**#Core::When::Prehistory**
This tag applies when the question pertains to the period before written records, typically covering human evolution, Stone Age cultures, cave paintings, megalithic structures, and early human migrations. For example, "What era is characterized by the use of polished stone tools?" or "Where were the Lascaux cave paintings discovered?".

**#Core::When::AncientHistory**
This tag applies when the question concerns the period from the beginning of written records (approx. 3000 BCE) to the fall of major classical empires (e.g., Western Roman Empire, approx. 500 CE). It covers civilizations like Mesopotamia, Ancient Egypt, Ancient Greece, Ancient Rome, early China, and the Indus Valley. Example: "Who was the first Roman Emperor?".

**#Core::When::First-Millenium-And-Medieval-Ages**
This tag applies when the question relates to the period roughly from 500 CE to 1400/1500 CE. This includes the Byzantine Empire, the rise of Islam, the European Middle Ages (Feudalism, Vikings, Crusades), the Mongol Empire, and developments in China and India during this time. Example: "Which English king signed the Magna Carta in 1215?".

**#Core::When::Renaissance**
This tag applies when the question focuses specifically on the European Renaissance period, roughly spanning the 14th to the 17th century. Key aspects include the revival of classical art and learning, humanism, major artistic figures (Da Vinci, Michelangelo), scientific advances, and the Age of Exploration's beginnings. Example: "Which Florentine family were major patrons of Renaissance art?".

**#Core::When::Early-Modern-And-Industrial-Era**
This tag applies when the question covers the period from roughly 1500 CE to the late 19th century (around 1900). This encompasses the Age of Exploration, the Reformation, the Scientific Revolution, the Enlightenment, major European monarchies, colonization, the American and French Revolutions, and the Industrial Revolution. Example: "Which invention is James Watt most famous for improving?".

**#Core::When::Twentieth-Century**
This tag applies when the question pertains to events, figures, or developments occurring between 1901 and 2000. This vast period includes World War I, the Russian Revolution, the Great Depression, World War II, the Cold War, decolonization, the rise of mass media, and major technological advancements. Example: "In what decade did the Cold War officially end?".

**#Core::When::Twenty-First-Century**
This tag applies when the question relates to events, figures, or developments occurring from 2001 onwards. This includes the September 11th attacks, the War on Terror, the rise of the internet and social media, the global financial crisis of 2008, recent technological innovations, and contemporary global issues. Example: "Which company launched the first iPhone in 2007?".

**#Core::When::Recent-Developments**
This tag applies when the question focuses on very recent events or developments, typically within the last few years or even months, that haven't yet become established historical facts but are significant current knowledge. It overlaps with Current Affairs but might refer to slightly less immediate news. Example: "Which country recently became the newest member of NATO?".

**#Core::When::Current-Affairs**
This tag applies when the question concerns events, situations, or figures that are currently unfolding or are prominent in the news cycle at the present moment (typically within the last year or less). This requires up-to-date knowledge of ongoing global or national events. Example: "Who is the current Secretary-General of the United Nations?".

**#Core::When::Predicted-To-Happen**
This tag applies when the question asks about future events, forecasts, predictions, or planned occurrences. This could relate to scientific projections, scheduled events (like future Olympics), or anticipated political or technological changes. Example: "Which city is scheduled to host the 2028 Summer Olympics?".

**#Core::When::Spans-Multiple-Timeperiods**
This tag applies when the question's subject matter inherently covers or compares developments across two or more distinct historical periods as defined by the other 'When' tags. For example, a question about the evolution of democracy from Ancient Greece to modern times, or tracing the history of a technology from its invention to the present day.

**#Subject::Art**
This tag applies broadly when the question relates to the fine arts, performing arts, or applied arts in general, without necessarily fitting into a more specific sub-category, or when the question touches upon multiple art forms. It serves as a high-level classifier for the domain of artistic expression.

**#Subject::Art::Painting-Printmaking-Drawing-And-2D-Art**
This tag applies when the question is specifically about painting (styles, artists, specific works), printmaking techniques (etching, lithography), drawing, or other forms of two-dimensional visual art like illustration or collage. Example: "Which Dutch master painted 'The Night Watch'?".

**#Subject::Art::Sculpture-Installations-And-3D-Art**
This tag applies when the question focuses on three-dimensional art forms, including sculpture (materials, sculptors, famous works), installation art, kinetic art, or land art. Example: "Who sculpted 'The Thinker'?".

**#Subject::Art::Photography**
This tag applies when the question is specifically about the art and practice of photography, including famous photographers, iconic photographs, photographic techniques, or the history of photography. Example: "Which photographer is known for her portraits taken during the Great Depression, such as 'Migrant Mother'?".

**#Subject::Art::Calligraphy**
This tag applies when the question pertains to the art of decorative handwriting or lettering, known as calligraphy, across various cultures and scripts (e.g., Chinese, Islamic, Western). It could involve specific styles, masters, or tools. Example: "What style of highly ornamental Islamic calligraphy is characterized by its interwoven letters?".

**#Subject::Art::Colours**
This tag applies when the question focuses specifically on colors, including color theory, the history or origin of specific pigments (like Ultramarine or Tyrian Purple), symbolism of colors in art, or scientific aspects of color perception related to art. Example: "What primary colors are mixed to create green?".

**#Subject::Art::Theatre-Drama-And-Musicals**
This tag applies when the question relates to live theatrical performances, including plays (playwrights, famous works, characters), drama as a genre, musical theatre (composers, lyricists, famous shows), stagecraft, or acting theory. Example: "Which Andrew Lloyd Webber musical features the song 'Memory'?".

**#Subject::Art::Dancing**
This tag applies broadly when the question is about dance as a performing art, covering various styles not specified in other sub-categories, famous dancers or choreographers (unless specific to ballet/classical), or general concepts in dance. Example: "Who is often called the 'Mother of Modern Dance'?".

**#Subject::Art::Ballet**
This tag applies when the question is specifically about the classical dance form of ballet, including its history, famous ballets (like 'Swan Lake'), renowned ballet companies, specific techniques or positions, choreographers, or principal dancers. Example: "Which Russian composer wrote the music for the ballets 'The Nutcracker' and 'Sleeping Beauty'?".

**#Subject::Art::Classical-Dances**
This tag applies when the question pertains to established traditional dance forms from specific cultures, often with codified techniques and historical significance, particularly those outside the Western ballet tradition (e.g., Indian classical dances like Bharatanatyam, Kathak; Japanese Noh). Example: "Which Indian classical dance form originated in Tamil Nadu?".

**#Subject::Art::Folk-Dance**
This tag applies when the question is about traditional dances associated with specific communities or ethnic groups, often performed socially or ceremonially, reflecting the life and culture of a region. Examples include Irish step dancing, Morris dancing, or the Indian Bhangra. Example: "The 'Hora' is a traditional circle folk dance associated with which region/culture?".

**#Subject::Art::Circus-And-Comedy**
This tag applies when the question relates to circus arts (acrobatics, clowning, juggling, aerial acts) or forms of comedic performance (stand-up comedy, sketch comedy, famous comedians, comedic troupes). Example: "Which Canadian contemporary circus troupe is known for its spectacular, character-driven shows without animals?".

**#Subject::Art::Architecture-And-Landscaping**
This tag applies when the question focuses on the art and science of designing buildings (architects, architectural styles, famous structures) or modifying the visible features of an area of land (landscape architecture, garden design, famous parks). Example: "Which architect designed the Guggenheim Museum in Bilbao, Spain?".

**#Subject::Art::Pottery-Ceramics-ObjetDArt-And-Applied-Arts**
This tag applies when the question concerns the creation of functional or decorative objects from clay (pottery, ceramics), finely crafted small decorative items (objets d'art), or other applied arts like jewelry making, tapestry, or decorative glasswork where aesthetic considerations are paramount. Example: "What type of Japanese pottery is known for its asymmetrical shapes and natural-looking glazes, often used in tea ceremonies?".

**#Subject::Design**
This tag applies broadly to questions about the principles and practice of design across various fields, including aesthetics, functionality, and the process of creating products, systems, or visuals. It serves as a general category if a more specific design sub-type isn't applicable.

**#Subject::Design::Graphic-Design**
This tag applies when the question focuses on visual communication design, including logo design, typography arrangement, poster design, advertising visuals, page layout, or famous graphic designers. Example: "Which graphic designer created the iconic 'I ❤ NY' logo?".

**#Subject::Design::Industrial-Design**
This tag applies when the question concerns the design of mass-produced products, focusing on their form, function, usability, ergonomics, and aesthetics. It involves items from furniture and appliances to vehicles and electronic devices. Example: "Which German company, associated with designer Dieter Rams, is known for its functionalist approach to designing consumer products?".

**#Subject::Design::Typography**
This tag applies when the question is specifically about the design and use of typefaces (fonts), including font classification (serif, sans-serif), famous type designers, the history of type, or principles of typesetting and layout. Example: "What is the term for the small decorative stroke attached to the end of a larger stroke in a letter, characteristic of serif fonts?".

**#Subject::Design::A-Design-Inspired-By-Something**
This tag applies when the question highlights a design (product, building, graphic, etc.) whose form, function, or concept was directly influenced or inspired by another object, natural phenomenon, artwork, or idea. Example: "The shape of the Sydney Opera House is famously inspired by what objects?".

**#Subject::Music**
This tag applies broadly to questions about music in general, covering aspects like music theory, history across genres, or general musical concepts, especially if the question doesn't fit neatly into a specific genre or instrument category.

**#Subject::Music::Opera**
This tag applies when the question is specifically about opera, including famous operas, composers (like Verdi, Puccini, Mozart), librettists, famous arias, opera houses, or specific singers known for operatic roles. Example: "In which Mozart opera does the character Figaro appear?".

**#Subject::Music::Classical-Music**
This tag applies when the question pertains to Western art music, often referred to as classical music, covering composers (Bach, Beethoven, Stravinsky), periods (Baroque, Classical, Romantic, Modern), forms (symphony, concerto, sonata), orchestras, or famous instrumental works. Example: "How many symphonies did Beethoven compose?".

**#Subject::Music::Jazz**
This tag applies when the question focuses on the jazz genre, including its origins, subgenres (swing, bebop, cool jazz), influential musicians (Louis Armstrong, Duke Ellington, Miles Davis), improvisation, or famous jazz standards. Example: "What instrument did jazz legend John Coltrane primarily play?".

**#Subject::Music::Rock**
This tag applies when the question relates to rock music, encompassing its various subgenres (classic rock, hard rock, punk rock, alternative rock), influential bands and artists (The Beatles, Led Zeppelin, Nirvana), iconic albums, or the history of the genre. Example: "Which band released the influential 1977 album 'Never Mind the Bollocks, Here's the Sex Pistols'?".

**#Subject::Music::Pop**
This tag applies when the question concerns popular music, typically chart-oriented music intended for a wide audience, including pop stars (Michael Jackson, Madonna, Taylor Swift), producers, hit songs, music videos, or trends in mainstream music. Example: "Which artist is known as the 'Queen of Pop'?".

**#Subject::Music::World-Music**
This tag applies when the question pertains to musical traditions from around the globe, particularly non-Western genres or folk music traditions that have gained international recognition (e.g., Reggae, Bossa Nova, Celtic music, various African genres). Example: "Which country is the birthplace of Reggae music?".

**#Subject::Music::Other-Genres-Or-Types-Of-Music**
This tag applies when the question is about musical genres or categories not covered by the specific tags above, such as blues, country, folk, electronic dance music (EDM), hip-hop, R&B, soul, film scores, or experimental music. Example: "Which city is considered the birthplace of Hip Hop culture?".

**#Subject::Music::Instruments**
This tag applies when the question focuses specifically on musical instruments, including their construction, history, classification (strings, brass, woodwind, percussion), famous players associated with specific instruments, or unique instruments. Example: "The Theremin is unique for being played without what?".

**#Subject::Literature**
This tag applies broadly to questions about written works, authors, literary movements, or literary theory in general, especially if the work doesn't fit clearly into a specific genre sub-category or if the question covers multiple aspects of literature.

**#Subject::Literature::Genre-Fiction**
This tag applies when the question relates to fiction categories characterized by specific conventions and tropes, such as science fiction, fantasy, mystery, thriller, romance, horror, or historical fiction. It includes authors, works, characters, or elements typical of these genres. Example: "Who wrote the 'A Song of Ice and Fire' fantasy series?".

**#Subject::Literature::Literary-Fiction**
This tag applies when the question concerns fiction that emphasizes character development, thematic depth, artistic merit, and complexity, often not fitting neatly into standard genre conventions. It includes authors and works typically studied for their literary value. Example: "Which novel by Gabriel Garcia Marquez begins with the line 'Many years later, as he faced the firing squad...'?".

**#Subject::Literature::Non-Fiction**
This tag applies when the question is about factual prose works, including history books, biographies, autobiographies (distinct from memoirs), science writing, journalism (in book form), or academic texts written for a general audience. Example: "Who wrote 'A Brief History of Time'?".

**#Subject::Literature::Essays-Memoirs-Etc**
This tag applies when the question focuses on shorter non-fiction forms like essays, personal memoirs (focusing on specific experiences rather than a whole life), diaries, letters, or speeches considered as literary works. Example: "Which French philosopher is credited with popularizing the essay form?".

**#Subject::Literature::Legends-Epics-Myths-Folktales**
This tag applies when the question relates to traditional stories passed down through generations, including myths (explaining origins or supernatural events), legends (often based on historical figures but embellished), epics (long narrative poems about heroic deeds), and folktales (stories of common people, often with a moral). Example: "Which epic poem tells the story of the Trojan War?". (Note overlap with Mythology).

**#Subject::Literature::Oral-Literature**
This tag applies when the question pertains to literary traditions transmitted verbally rather than through writing, including spoken word poetry, storytelling traditions, chants, or performance-based narratives from various cultures before or alongside written forms. Example: "The Griots of West Africa are known for preserving what form of literature?".

**#Subject::Literature::Comics-And-Graphic Novels**
This tag applies when the question is about sequential art narratives, including comic books (superhero, indie), graphic novels (longer, often self-contained stories), manga, or bande dessinée. It covers creators, characters, publishers, and specific works. Example: "Who created the comic book characters Superman and Batman?".

**#Subject::Literature::Comic-Strips**
This tag applies when the question focuses on short-form comics typically published in newspapers or online, often featuring recurring characters and telling jokes or brief stories over a few panels. Examples include 'Peanuts', 'Calvin and Hobbes', or 'Garfield'. Example: "Which comic strip features a boy named Charlie Brown and his beagle, Snoopy?".

**#Subject::Movies**
This tag applies broadly to questions about cinema and filmmaking in general, covering aspects like film history, directing, cinematography, acting, or general film terminology, especially if not specific to a particular regional cinema or genre like animation.

**#Subject::Movies::Hollywood**
This tag applies when the question specifically concerns the mainstream American film industry centered around Hollywood, including its major studios, stars, directors, iconic films, genres strongly associated with Hollywood (e.g., Westerns), or historical periods like the Golden Age. Example: "Which film won the first Academy Award for Best Picture?".

**#Subject::Movies::Bollywood**
This tag applies when the question is specifically about the Hindi-language film industry based in Mumbai, India, known as Bollywood. This includes its characteristic musical numbers, famous actors (like Shah Rukh Khan, Amitabh Bachchan), directors, popular films, or common themes. Example: "Which 1995 Bollywood film, starring Shah Rukh Khan and Kajol, is one of the longest-running films in Indian cinema history?".

**#Subject::Movies::World-Cinema**
This tag applies when the question pertains to films or filmmaking traditions from countries outside the dominant US (Hollywood) and Indian (Bollywood) industries. This includes European cinema (French New Wave, Italian Neorealism), East Asian cinema (Japanese, Korean, Chinese films), Latin American cinema, African cinema, etc. Example: "Which Italian director is known for films like 'La Dolce Vita' and '8½'?".

**#Subject::Movies::Animation**
This tag applies when the question is specifically about animated films or animation techniques, including traditional cel animation, stop-motion, CGI, famous animation studios (Disney, Pixar, Studio Ghibli), animators, or iconic animated characters and films. Example: "Which Studio Ghibli film features the characters Totoro and Catbus?".

**#Subject::Broadcasting**
This tag applies broadly to questions related to the distribution of audio or video content to a dispersed audience via electronic mass communications media, like radio and television, especially if the content type isn't specified by a sub-category.

**#Subject::Broadcasting::TelevisionTV-Fictional**
This tag applies when the question concerns scripted television programs, including dramas, comedies (sitcoms), science fiction series, soap operas, miniseries, famous characters, actors known for TV roles, or show creators. Example: "Which television series features the characters Walter White and Jesse Pinkman?".

**#Subject::Broadcasting::TelevisionTV-Nonfiction**
This tag applies when the question relates to non-scripted television content, such as documentaries, reality TV shows, game shows, talk shows, news programs (see also NEWS), or educational programming. Example: "Which long-running American game show involves contestants guessing prices of merchandise?".

**#Subject::Broadcasting::NEWS**
This tag applies specifically when the question is about television or radio news broadcasting, including news anchors, famous news programs or networks, historical news broadcasts, or the practice of broadcast journalism. (Can overlap with Media::NEWS-Media). Example: "Which American journalist was known for his CBS Evening News sign-off, 'And that's the way it is'?".

**#Subject::Broadcasting::Radio-And-Podcasts**
This tag applies when the question focuses on audio broadcasting, including the history of radio, famous radio shows or personalities, radio dramas, specific radio stations or networks, or the more recent medium of podcasts (creators, popular shows, platforms). Example: "Orson Welles's 1938 radio broadcast of which story caused panic among some listeners?".

**#Subject::Media**
This tag applies broadly to questions concerning mass communication channels and industries, including print, digital, and broadcast media, especially when discussing media ownership, influence, or general concepts not specific to one format.

**#Subject::Media::NEWS-Media**
This tag applies when the question is about the news industry as a whole, encompassing newspapers, news agencies (like Reuters, AP), news magazines, online news platforms, photojournalism, famous journalists, or the principles and ethics of journalism. (Can overlap with Broadcasting::NEWS). Example: "Which two Washington Post reporters were central to uncovering the Watergate scandal?".

**#Subject::Media::Mixed-Media-Work**
This tag applies when the question refers to artworks, presentations, or projects that combine different media forms, such as integrating video, sound, text, and images, often in an installation or digital context. Example: "What term describes an art form that combines visual art with sound, text, and motion?".

**#Subject::Media::Other**
This tag applies to questions about media forms or concepts not covered by the other specific media tags, potentially including outdoor advertising (billboards), direct mail, or theoretical aspects of media studies not focused on news, social media, or mixed media.

**#Subject::Media::Social-Media**
This tag applies when the question specifically relates to online platforms and services that facilitate social networking and content sharing, such as Facebook, Twitter, Instagram, TikTok, LinkedIn, including their features, history, impact, or associated terminology. Example: "Which social media platform is known for its 280-character limit for posts?".

**#Subject::Culture**
This tag applies broadly to questions about the shared customs, arts, social institutions, beliefs, and achievements of a particular nation, people, or group. It acts as a general category for the humanistic aspects of societies.

**#Subject::Culture::High-Culture**
This tag applies when the question relates to cultural products and practices considered aesthetically superior or associated with elite or educated groups, such as classical music, opera, ballet, fine art, literary fiction, and intellectual pursuits. Example: "Which art form is typically considered part of 'high culture': opera or street art?".

**#Subject::Culture::Popular-Culture**
This tag applies when the question concerns cultural products, trends, and practices widely shared and consumed by the mainstream population, including pop music, blockbuster movies, best-selling genre fiction, television shows, celebrity news, fashion trends, and widely adopted slang. Example: "Which decade is strongly associated with disco music and bell-bottom pants in popular culture?".

**#Subject::Culture::Folk-Culture**
This tag applies when the question relates to the traditional customs, beliefs, practices, art forms (like folk music, dance, crafts), and stories of a specific community, often rural, non-elite, and passed down through generations. Example: "What traditional craft involves decorating eggs, often associated with Easter traditions in Eastern Europe?".

**#Subject::Culture::Celebrity-Culture**
This tag applies when the question focuses on the lives, careers, and public fascination with famous individuals (celebrities), including actors, musicians, athletes, socialites, and reality TV stars, as well as phenomena like paparazzi and gossip magazines. Example: "What term describes an intense, often short-lived, romantic relationship between two high-profile celebrities?".

**#Subject::Culture::Internet-Culture**
This tag applies when the question pertains to the slang, memes, trends, social norms, communities, and phenomena that have emerged specifically from online interactions and digital environments. Example: "What term refers to an image, video, piece of text, etc., typically humorous in nature, that is copied and spread rapidly by Internet users?".

**#Subject::Culture::Subcultures**
This tag applies when the question concerns distinct cultural groups existing within a larger society, characterized by their own specific beliefs, values, styles, or practices that differentiate them from the mainstream (e.g., Goths, Punks, Skaters, specific fandoms). Example: "Which subculture, originating in the UK in the late 1970s, is associated with dark clothing, gothic rock music, and an interest in the macabre?".

**#Subject::Culture::Countercultures**
This tag applies when the question relates to subcultures whose values and norms of behavior differ substantially from, and often consciously oppose, those of mainstream society. Examples include the Beat Generation, the Hippie movement of the 1960s, or early Punk movements. Example: "Which 1960s counterculture movement advocated peace, love, and psychedelic experiences?".

**#Subject::Culture::Norms-And-Etiquette**
This tag applies when the question focuses on the accepted standards of behavior, social rules, customs, and etiquette within a particular society or group. This could involve table manners, forms of address, gift-giving customs, or dress codes. Example: "In Japan, is it considered polite or impolite to tip for service in restaurants?".

**#Subject::Heritage**
This tag applies broadly to questions concerning aspects inherited from the past that are considered valuable, including traditions, cultural artifacts, historical sites, and significant cultural legacies.

**#Subject::Heritage::Museums**
This tag applies when the question is specifically about museums, including famous institutions (like the Louvre, British Museum, Smithsonian), types of museums (art, history, science), specific exhibits, curation practices, or museum architecture. Example: "Which museum in Paris houses the 'Mona Lisa'?".

**#Subject::Heritage::Galleries**
This tag applies when the question focuses on art galleries, spaces primarily dedicated to the exhibition (and sometimes sale) of visual art, including famous commercial or public galleries, specific exhibitions, or the role of galleries in the art world. Example: "What is the name of the national gallery of modern art located in London, housed in a former power station?".

**#Subject::Heritage::Monuments-And-Culturally-Important-Locations**
This tag applies when the question pertains to physical structures (monuments, statues, buildings) or specific locations (archaeological sites, historical districts, natural landmarks) recognized for their historical, cultural, or symbolic significance. Example: "Which ancient citadel in Athens contains the Parthenon?".

**#Subject::Heritage::Memorials**
This tag applies when the question is specifically about structures, sites, or objects created to commemorate a person, event, or group, often related to remembrance of loss, sacrifice, or significant historical moments (e.g., war memorials, Holocaust memorials). Example: "What DC landmark features a long black granite wall inscribed with the names of American service members who died in the Vietnam War?".

**#Subject::Heritage::Icons-And-Symbols**
This tag applies when the question concerns objects, images, figures, or emblems that hold significant symbolic meaning or represent broader concepts, identities, or cultural values within a society or group (e.g., national flags, religious symbols, iconic brand logos with cultural weight). Example: "What bird is a national symbol of the United States?".

**#Subject::Philosophy**
This tag applies broadly to questions concerning the fundamental nature of knowledge, reality, existence, ethics, logic, and reason. It includes philosophical traditions, concepts, and major thinkers.

**#Subject::Philosophy::Ethics**
This tag applies when the question specifically relates to the branch of philosophy dealing with moral principles, concepts of right and wrong conduct, justice, virtue, and moral dilemmas. It includes ethical theories (like utilitarianism, deontology) and applied ethics. Example: "What ethical theory suggests that the best action is the one that maximizes overall happiness or utility?".

**#Subject::Philosophy::Ideology**
This tag applies when the question concerns systems of ideas, beliefs, and doctrines that form the basis of economic, political, or social theories and policies. Examples include liberalism, conservatism, socialism, communism, fascism, feminism, nationalism. Example: "Which political ideology emphasizes individual liberty, private property, and limited government intervention?".

**#Subject::Religion**
This tag applies broadly to questions about organized systems of belief, worship, and practices related to the sacred or divine, including general concepts of religion, comparative religion, or aspects common to multiple faiths.

**#Subject::Religion::Islam**
This tag applies when the question specifically concerns Islam, including its beliefs (Five Pillars), holy book (Quran), prophet (Muhammad), denominations (Sunni, Shia), practices, history, holy sites (Mecca, Medina), or cultural aspects. Example: "What is the name of the holy month of fasting observed by Muslims?".

**#Subject::Religion::Hinduism**
This tag applies when the question specifically concerns Hinduism, including its diverse traditions, deities (Brahma, Vishnu, Shiva, Devi), scriptures (Vedas, Upanishads, Bhagavad Gita), concepts (karma, dharma, reincarnation), caste system, festivals (Diwali, Holi), or major philosophical schools. Example: "What is the Trimurti in Hinduism?".

**#Subject::Religion::Christianity**
This tag applies when the question specifically concerns Christianity, including its central figure (Jesus Christ), holy book (Bible), major branches (Catholicism, Protestantism, Orthodoxy), core beliefs (Trinity, resurrection), sacraments, historical development, or important figures. Example: "What are the first four books of the New Testament collectively called?".

**#Subject::Religion::Judaism**
This tag applies when the question specifically concerns Judaism, including its foundational texts (Torah, Talmud), central beliefs (monotheism, covenant), practices (Sabbath, dietary laws/kashrut), holidays (Passover, Hanukkah), historical periods, or branches (Orthodox, Conservative, Reform). Example: "What is the Hebrew term for the Jewish Sabbath?".

**#Subject::Religion::Sikhism**
This tag applies when the question specifically concerns Sikhism, including its founder (Guru Nanak), subsequent Gurus, holy scripture (Guru Granth Sahib), core beliefs (monotheism, equality, service/seva), practices (the Five Ks), or important sites (Golden Temple). Example: "What is the name of the community kitchen found in Sikh Gurdwaras, serving free meals to all?".

**#Subject::Religion::Animistic-Beliefs**
This tag applies when the question relates to belief systems where spirits or souls are attributed to natural objects, phenomena, and living beings (plants, animals, rocks, rivers). It often pertains to indigenous or tribal religions. Example: "What general term describes the belief that spirits inhabit natural objects and phenomena?".

**#Subject::Religion::Other-Religions**
This tag applies when the question concerns specific religions not covered by the dedicated tags, such as Buddhism, Jainism, Shinto, Taoism, Baha'i Faith, Zoroastrianism, or smaller religious movements. Example: "What religion follows the teachings of Siddhartha Gautama?".

**#Subject::Religion::New-Age-Belief-Systems**
This tag applies when the question relates to modern spiritual or religious movements characterized by an eclectic mix of beliefs drawn from various sources, often emphasizing spirituality, mysticism, self-help, and alternative healing (e.g., beliefs in crystals, astrology, channeling). Example: "What practice, often associated with New Age beliefs, involves interpreting celestial bodies' influence on human affairs?".

**#Subject::Religion::Other-Belief-Systems**
This tag applies when the question concerns organized systems of belief that function similarly to religions but may not involve a deity, such as certain philosophical systems with strong ethical codes (like Confucianism when viewed as a belief system), or specific non-theistic spiritual paths. It can also cover atheism or agnosticism as stances on belief.

**#Subject::Mythology**
This tag applies broadly to questions about traditional stories, especially those concerning the early history of a people or explaining natural or social phenomena, typically involving supernatural beings or events. It includes pantheons, mythical creatures, and legendary heroes across cultures (Greek, Roman, Norse, Egyptian, etc.). (Can overlap with Literature::Legends-Epics-Myths-Folktales and Religion).

**#Subject::Mythology::Folklore-And-Folk-Beliefs**
This tag applies when the question focuses specifically on the traditional beliefs, customs, legends, and stories of a community passed down through generations, often orally. This includes superstitions, folk remedies, local legends, proverbs, and mythical creatures from folk tradition (distinct from grand, classical myth systems). Example: "According to European folklore, what creature is said to transform during a full moon?".

**#Subject::Language-And-Linguistics**
This tag applies broadly to questions about human language, including its structure, history, acquisition, use, and the scientific study of language (linguistics). It covers grammar, phonetics, semantics, pragmatics, and sociolinguistics.

**#Subject::Language-And-Linguistics::Etymology**
This tag applies when the question specifically asks about the origin and historical development of a word, tracing its roots, changes in meaning, and connections to other languages. Example: "The word 'salary' originates from the Latin word 'salarium', which referred to money paid to Roman soldiers for what commodity?".

**#Subject::Language-And-Linguistics::Slang**
This tag applies when the question concerns informal words or phrases, often specific to a particular group, region, or time period, that are not part of standard vocabulary. Example: "In British slang, what does the term 'gobsmacked' mean?".

**#Subject::Language-And-Linguistics::Words-From-Non-English**
This tag applies when the question focuses on words or concepts from languages other than English, perhaps asking for their meaning, origin, or cultural context, often because they represent ideas not easily translated. Example: "What does the German word 'Schadenfreude' mean?".

**#Subject::Language-And-Linguistics::Loanwords-And-Imported-Words**
This tag applies when the question is about words adopted from one language (the source language) into another language (the recipient language) with little or no modification. Example: "The English words 'ballet', 'menu', and 'croissant' are loanwords from which language?".

**#Subject::Language-And-Linguistics::Technical-Words-Or-Jargon**
This tag applies when the question involves specialized terminology used within a particular profession, field of study, or activity, which might be unfamiliar to outsiders. Example: "In medicine, what does the acronym 'MRI' stand for?".

**#Subject::Language-And-Linguistics::Neologisms**
This tag applies when the question concerns newly coined words or expressions, or existing words used in a new sense, that are in the process of entering common use. Example: "What neologism describes the fear of being without one's mobile phone?".

**#Subject::Language-And-Linguistics::Buzzwords**
This tag applies when the question relates to words or phrases, often fashionable or trendy, used more to impress or catch attention than for precise meaning, particularly common in business, technology, or marketing. Example: "What business buzzword refers to a disruptive innovation that creates a new market and value network?".

**#Subject::Language-And-Linguistics::Written-Language-And-Scripts**
This tag applies when the question focuses on writing systems, alphabets, characters, scripts (e.g., Cyrillic, Arabic, Kanji), hieroglyphs, calligraphy (as a system, distinct from art), paleography (study of ancient writing), or the history of writing. Example: "Which ancient Egyptian script consisted of stylized pictures representing words or sounds?".

**#Subject::Sports**
This tag applies broadly to questions about competitive physical activities and games, including rules, history, famous athletes, major events, or general sporting terminology.

**#Subject::Sports::Athletics-And-Gymnastics**
This tag applies when the question specifically concerns track and field events (running, jumping, throwing), road running, cross country running, race walking, or gymnastics disciplines (artistic, rhythmic, trampoline). Example: "Who holds the current men's 100m sprint world record?".

**#Subject::Sports::Football**
This tag applies when the question is about Association Football (Soccer), including rules, major tournaments (FIFA World Cup, UEFA Champions League), famous clubs, legendary players (Pelé, Maradona, Messi, Ronaldo), or national teams. Example: "Which country has won the most FIFA World Cup titles?".

**#Subject::Sports::Cricket**
This tag applies when the question concerns the sport of cricket, including its rules (Test, ODI, T20 formats), terminology (LBW, wicket, boundary), major competitions (ICC Cricket World Cup, The Ashes), famous players, or national teams. Example: "How many balls are typically bowled in one over in cricket?".

**#Subject::Sports::Basketball**
This tag applies when the question is about basketball, including rules, leagues (NBA, EuroLeague), famous teams, legendary players (Michael Jordan, LeBron James), or key concepts like slam dunks or three-pointers. Example: "Which NBA team has won the most championships?".

**#Subject::Sports::American-Football**
This tag applies when the question concerns American Football, including rules, positions, leagues (NFL, college football), famous teams, the Super Bowl, legendary players, or key plays like touchdowns or field goals. Example: "What is the name of the NFL championship game held annually?".

**#Subject::Sports::Golf**
This tag applies when the question is about golf, including rules, scoring (par, bogey, birdie), major championships (The Masters, The Open), famous courses, legendary golfers (Jack Nicklaus, Tiger Woods), or equipment. Example: "What is the term for scoring one stroke under par on a golf hole?".

**#Subject::Sports::Tennis**
This tag applies when the question concerns tennis, including rules, scoring (love, deuce, advantage), Grand Slam tournaments (Wimbledon, US Open, French Open, Australian Open), famous players (Federer, Nadal, Djokovic, Williams sisters), or court surfaces. Example: "Which Grand Slam tennis tournament is played on clay courts?".

**#Subject::Sports::Other-Ball-Sports**
This tag applies when the question relates to ball sports not covered by the specific tags above, such as baseball, softball, volleyball, handball, rugby (Union and League), field hockey, ice hockey, lacrosse, water polo, etc. Example: "In baseball, how many strikes result in a batter being out?".

**#Subject::Sports::Combat-Sports**
This tag applies when the question concerns competitive contact sports that usually involve one-on-one competition, such as boxing, wrestling (freestyle, Greco-Roman), martial arts (judo, karate, taekwondo), mixed martial arts (MMA), fencing, or sumo wrestling. Example: "Which martial art, originating in Korea, is known for its emphasis on high kicks?".

**#Subject::Sports::Motorsport**
This tag applies when the question relates to competitive sporting events primarily involving motorized vehicles, including Formula 1, NASCAR, IndyCar, rally racing, MotoGP, endurance racing (like Le Mans), or drag racing. Example: "Which city hosts the famous Monaco Grand Prix Formula 1 race?".

**#Subject::Sports::Adventure-Sports**
This tag applies when the question concerns sports often involving high risk, specialized skills, and interaction with natural environments, such as rock climbing, mountaineering, kayaking, whitewater rafting, surfing, snowboarding, skydiving, or BASE jumping. Example: "What adventure sport involves navigating river rapids in an inflatable raft?".

**#Subject::Sports::Watersports**
This tag applies when the question focuses on sports performed in or on water, excluding swimming (often under Athletics) unless specifically competitive swimming events. Includes sailing, windsurfing, kitesurfing, rowing, canoeing, diving (platform/springboard), synchronized swimming, or surfing (can overlap with Adventure). Example: "In competitive rowing, what is the term for the person who steers the boat and coordinates the crew?".

**#Subject::Sports::Equestrian-Sports**
This tag applies when the question relates to sports involving horses, such as show jumping, dressage, eventing, horse racing (thoroughbred, harness), polo, or rodeo events. Example: "What equestrian event is often called 'horse ballet'?".

**#Subject::Sports::Other-Sports**
This tag applies when the question concerns sports not easily categorized into the other specific tags, such as archery, shooting, cycling (road, track, mountain biking), figure skating, skiing (alpine, cross-country), curling, bowling, weightlifting, or billiards/snooker. Example: "In which Winter Olympic sport do teams slide stones on a sheet of ice towards a target area?".

**#Subject::Sports::Parasports**
This tag applies when the question relates to sports practiced by people with disabilities, including adaptations of existing sports or sports specifically designed for athletes with impairments. Often associated with the Paralympics. Example: "What sport, played by visually impaired athletes, involves throwing a ball with bells inside towards the opponent's goal?".

**#Subject::Sports::Olympics**
This tag applies when the question is specifically about the Summer or Winter Olympic Games, including host cities, specific events, medal history, Olympic symbols (rings, torch), the IOC, or famous Olympians across various sports discussed in the context of the Games. Example: "In which city were the first modern Olympic Games held in 1896?".

**#Subject::Sports::Paralympics**
This tag applies when the question is specifically about the Paralympic Games, the major international multi-sport event involving athletes with a range of disabilities. Includes host cities, specific Para sports, classification systems, or famous Paralympians. Example: "The Paralympic Games are typically held shortly after which other major international sporting event?".

**#Subject::Sports::Winter-Olympics**
This tag applies when the question is specifically about the Winter Olympic Games, focusing on sports practiced on snow or ice, host cities, medal history, or athletes famous for Winter Olympic achievements. Example: "Which country has won the most medals in the history of the Winter Olympics?".

**#Subject::Games**
This tag applies broadly to questions about recreational activities involving skill, strategy, or chance, played according to rules, often for amusement or competition, excluding physical sports covered elsewhere.

**#Subject::Games::Chess**
This tag applies when the question is specifically about the game of chess, including its rules, pieces, openings, tactics, famous players (world champions like Kasparov, Carlsen), history, or terminology (checkmate, stalemate). Example: "What is the only chess piece that can leap over other pieces?".

**#Subject::Games::Other-Board-Games**
This tag applies when the question concerns board games other than chess, such as Monopoly, Scrabble, Settlers of Catan, Go, Backgammon, Draughts/Checkers, or modern strategy board games. Includes rules, history, designers, or specific game elements. Example: "In the board game Monopoly, what are the four railroad properties?".

**#Subject::Games::Card-Games**
This tag applies when the question relates to games played using playing cards, such as Poker, Bridge, Rummy, Solitaire, Blackjack, Tarot (as a game), or collectible card games like Magic: The Gathering or Pokémon TCG. Includes rules, terminology, hand rankings, or history. Example: "In most poker variants, which hand ranks higher: a flush or a straight?".

**#Subject::Games::Traditional-Games**
This tag applies when the question concerns games passed down through generations within a culture, often played with simple or improvised equipment, including children's games (like tag, hide-and-seek), street games, or folk games specific to certain regions. Example: "What children's game involves one player covering their eyes and counting while others hide?".

**#Subject::Games::Video-Games-And-e-Sport**
This tag applies when the question is about electronic games played on computers, consoles, or mobile devices, including specific game titles (Mario, Zelda, Call of Duty), genres (RPG, FPS, MMO), developers, consoles (PlayStation, Xbox, Switch), history, or the phenomenon of competitive gaming (eSports). Example: "Which video game company created the characters Mario and Link?".

**#Subject::Law**
This tag applies broadly to questions concerning the system of rules that a particular country or community recognizes as regulating the actions of its members and may enforce by the imposition of penalties. It covers legal principles, institutions, and processes.

**#Subject::Law::Legal-System-And-Systems**
This tag applies when the question focuses on the structure, principles, and functioning of legal systems, such as common law versus civil law systems, branches of law (criminal, civil, constitutional), court structures, legal professions (judges, lawyers), or foundational legal concepts (due process, presumption of innocence). Example: "What is the highest court in the United States legal system?".

**#Subject::Law::Cases-And-Trials**
This tag applies when the question concerns specific landmark legal cases, famous trials, judicial decisions, precedents set by courts, or notable legal battles. Example: "Which landmark U.S. Supreme Court case established the principle of 'separate but equal', later overturned?".

**#Subject::Law::Crimes-And-Criminals**
This tag applies when the question relates to specific types of crimes (theft, murder, fraud), criminal law principles (mens rea, actus reus), famous criminals, criminal investigations, or forensic science as applied to law. Example: "What infamous Chicago gangster was finally imprisoned for tax evasion?".

**#Subject::Law::Rules-And-Regulations**
This tag applies when the question concerns specific laws, statutes, regulations, treaties, or legal codes governing particular activities or areas, such as traffic laws, environmental regulations, international treaties, or specific legislation passed by governing bodies. Example: "What international treaty, adopted in 1997, commits state parties to reduce greenhouse gas emissions?".

**#Subject::Society**
This tag applies broadly to questions about the structure, organization, functioning, and development of human societies, including social institutions, relationships, interactions, and collective behavior.

**#Subject::Society::Government**
This tag applies when the question concerns the systems and institutions through which a state or community is governed, including forms of government (democracy, monarchy, republic), branches of government (executive, legislative, judicial), political processes (elections, lawmaking), specific government bodies, or political leaders. Example: "In a parliamentary system, who is typically the head of government?".

**#Subject::Society::Diplomacy-And-International-Relations**
This tag applies when the question relates to the conduct of relationships between nations, including diplomacy, treaties, international organizations (like the UN, NATO, EU), foreign policy, ambassadors, summits, international conflicts (from a political perspective), and global cooperation. Example: "What international organization was founded after World War II to promote international peace and security?".

**#Subject::Society::Public-Services**
This tag applies when the question concerns services provided by the government to its citizens, either directly or through financing, such as public education, healthcare systems, social welfare programs, public transportation, utilities (water, electricity if state-run), and infrastructure maintenance. Example: "What is the common name for the UK's publicly funded healthcare system?".

**#Subject::Society::Social-Issues**
This tag applies when the question addresses problems or conditions within society that are seen as undesirable and requiring collective action or policy changes, such as poverty, inequality, discrimination, crime, public health crises, environmental degradation (as a societal problem), or education reform. Example: "What term describes the unequal distribution of wealth and opportunity within a society?".

**#Subject::Society::Anthropology**
This tag applies when the question relates to the scientific study of humans, human behavior, and societies, past and present, including cultural anthropology (study of cultures), physical anthropology (human evolution and biology), archaeology (study of human past through material remains), or linguistic anthropology. Example: "Which anthropologist wrote the influential works 'Coming of Age in Samoa' and 'Sex and Temperament in Three Primitive Societies'?".

**#Subject::Anti-Society**
This tag applies broadly to questions concerning movements, groups, individuals, or phenomena that challenge, oppose, or exist outside the established norms, structures, or authority of mainstream society.

**#Subject::Anti-Society::Social-Movements**
This tag applies when the question relates to organized efforts by groups of people to bring about or resist social, political, economic, or cultural change. Examples include the Civil Rights Movement, environmental movements, labor movements, or anti-globalization movements. Example: "Which social movement in the US during the 1950s and 1960s aimed to end racial segregation and discrimination?".

**#Subject::Anti-Society::Protests**
This tag applies when the question concerns specific instances or forms of public demonstration, dissent, or objection against policies, actions, or states of affairs, including marches, sit-ins, boycotts, riots, or specific historical protest events. Example: "What 1989 protest event in Beijing saw student-led demonstrations calling for democratic reforms?".

**#Subject::Anti-Society::Gender-Related-Movements-And-Struggles**
This tag applies when the question focuses specifically on movements advocating for gender equality, women's rights (feminism), LGBTQ+ rights, or challenging traditional gender roles and norms. It includes historical suffrage movements, feminist waves, or contemporary LGBTQ+ activism. Example: "What term refers to the movement advocating for voting rights for women?".

**#Subject::Anti-Society::Race-Related-Movements-And-Struggles**
This tag applies when the question focuses specifically on movements challenging racial inequality, discrimination, and injustice, such as the anti-apartheid movement, the American Civil Rights Movement, Black Lives Matter, or indigenous rights movements. Example: "Who was a major leader of the anti-apartheid movement in South Africa?".

**#Subject::Anti-Society::Religion-Related-Movements-And-Struggles**
This tag applies when the question concerns movements or conflicts arising from religious differences, persecution, or the struggle for religious freedom or dominance. This could include historical events like the Reformation (as a challenge to authority), religious conflicts, or movements advocating for secularism or opposing religious influence. Example: "What 16th-century movement led by Martin Luther challenged the authority of the Catholic Church?".

**#Subject::Anti-Society::Youth-Related-Movements-And-Struggles**
This tag applies when the question focuses on social or political movements primarily driven by young people, often expressing generational discontent, advocating for specific youth issues, or playing a key role in broader countercultural or protest movements (e.g., student protests of the 1960s). Example: "The student protests in Paris in May 1968 were part of a wider period of ________ unrest?".

**#Subject::Anti-Society::Class-Related-Movements-And-Struggles**
This tag applies when the question concerns movements arising from economic inequality and class conflict, such as labor union movements, socialist or communist revolutions, peasant revolts, or protests against economic policies perceived as unfair to lower or working classes. Example: "What 19th-century ideology, heavily influenced by Karl Marx, advocates for a classless society achieved through worker revolution?".

**#Subject::Anti-Society::Rebels-Or-Outlaws**
This tag applies when the question focuses on individuals or groups who openly defy authority, laws, or social conventions, often romanticized or viewed as symbols of resistance, even if engaged in criminal activity (e.g., Robin Hood, Jesse James, pirates, certain revolutionary figures). Example: "Which legendary English outlaw is said to have stolen from the rich and given to the poor?".

**#Subject::Anti-Society::Radicals-Or-Extremists**
This tag applies when the question concerns individuals, groups, or ideologies advocating for fundamental or extreme political, social, or religious changes, often employing unconventional or drastic methods. This term can be subjective but generally refers to positions far outside the mainstream consensus. Example: "The Jacobins were considered a ______ faction during the French Revolution?".

**#Subject::Anti-Society::Pariahs-Or-Exiles**
This tag applies when the question relates to individuals or groups who have been outcast, banished, or excluded from their society or community, either formally (exile) or informally (social pariahs). Example: "Which French emperor was famously exiled to the island of Elba and later St. Helena?".

**#Subject::Anti-Society::Freedom-Fighters**
This tag applies when the question concerns individuals or groups engaged in armed struggle or resistance against an occupying power, colonial rule, or oppressive regime, typically framed (by supporters) as fighting for liberty or national liberation. The term is often politically charged. Example: "The Viet Cong were guerrilla fighters opposing the US and South Vietnamese government during which war?".

**#Subject::World**
This tag applies broadly to questions about the Earth, its physical features, human populations, political divisions, and global-scale phenomena.

**#Subject::World::Physical-Geography**
This tag applies when the question concerns the natural features and processes of the Earth's surface, including landforms (mountains, rivers, deserts), climate, oceans, atmosphere, ecosystems, and plate tectonics. Example: "What is the longest river in the world?".

**#Subject::World::Human-Geography**
This tag applies when the question focuses on the spatial distribution of human populations, cultures, economies, settlements, and political entities across the Earth, and how humans interact with and modify their environment. Includes population density, urbanization, migration patterns, cultural landscapes. Example: "What term describes the movement of people from rural areas to cities?".

**#Subject::World::Exploration-And-Explorers**
This tag applies when the question concerns voyages, expeditions, and discoveries aimed at exploring unknown or remote regions of the Earth, including famous explorers (like Columbus, Magellan, Cook, Marco Polo), key expeditions, and the history of geographical discovery. Example: "Which explorer led the first European expedition to circumnavigate the globe?".

**#Subject::World::Countries-And-Their-Cities**
This tag applies when the question asks for identification, location, capitals, major cities, or specific characteristics of individual countries or their urban centers. Example: "What is the capital city of Canada?".

**#Subject::World::National-Identities-And-Identifiers**
This tag applies when the question relates to symbols, characteristics, or concepts associated with national identity, such as flags, anthems, national animals/plants, currencies, languages, demonyms (names for inhabitants, e.g., French, Japanese), or mottos. Example: "What is the national currency of Japan?".

**#Subject::World::Boundaries-And-Cartography**
This tag applies when the question concerns political borders between countries or regions, geographical boundaries (like the Equator, Tropics), time zones, map-making (cartography), map projections, or geographical coordinate systems (latitude, longitude). Example: "What line of latitude circles the Earth halfway between the North and South Poles?".

**#Subject::World::Famous-Places-And-Landmarks**
This tag applies when the question asks about specific well-known natural or man-made sites, landmarks, geographical features, or points of interest around the world (e.g., Eiffel Tower, Mount Everest, Grand Canyon, Great Barrier Reef). Example: "Which famous waterfall is located on the border between Zambia and Zimbabwe?".

**#Subject::World::Infrastructure**
This tag applies when the question concerns the fundamental facilities and systems serving a country, city, or area, including transportation networks (roads, railways, airports), communication systems, energy grids, water supply, and large-scale engineering projects like canals or dams. Example: "Which canal connects the Atlantic and Pacific Oceans through Central America?".

**#Subject::Transport**
This tag applies broadly to questions about the systems, means, and industries involved in moving people or goods from one place to another.

**#Subject::Transport::Locomotives**
This tag applies when the question specifically concerns trains, railways, subway systems, trams, engines that pull trains (locomotives), high-speed rail, or the history of rail transport. Example: "What was the name of the first intercity railway line, opened in England in 1830?".

**#Subject::Transport::Automotives**
This tag applies when the question relates to road vehicles, primarily cars, trucks, buses, and motorcycles, including manufacturers, models, history of the automobile, engine types, driving rules, or related technologies. Example: "Which German company produces the 911 sports car?".

**#Subject::Transport::Air-Transport**
This tag applies when the question concerns aviation, including airplanes, helicopters, airports, airlines, air traffic control, history of flight, famous aviators, or aerospace technology related to transport. Example: "Who were the Wright brothers, famous pioneers in aviation?".

**#Subject::Transport::Water-Transport**
This tag applies when the question relates to movement on water, including ships (cargo, passenger liners, ferries), boats, canals, ports, navigation, maritime history, submarines (for transport/exploration), or naval architecture related to transport vessels. Example: "What type of large ship is specifically designed to carry oil in bulk?".

**#Subject::Transport::Other**
This tag applies when the question concerns forms of transport not covered by the specific categories above, such as pipelines, cable cars, elevators/escalators, animal-powered transport (historically or currently), or emerging transport technologies like hyperloops.

**#Subject::Transport::Trade-And-Logistics**
This tag applies when the question focuses on the commercial aspects of transport, including the shipping industry, freight transport, supply chain management, logistics, trade routes (modern or historical), customs, or companies involved in moving goods. Example: "What term describes the management of the flow of things between the point of origin and the point of consumption?".

**#Subject::History**
This tag applies broadly to questions about past events, periods, figures, and the study of the past, especially when covering large scopes or general historical concepts not confined to a specific sub-category like military history or archaeology.

**#Subject::History::Archaeology-Sites-Findings-And-More**
This tag applies when the question concerns the study of human history and prehistory through the excavation of sites and the analysis of artifacts and other physical remains. Includes archaeological methods, archaeological sites (Pompeii, Machu Picchu or even less popular sites), discoveries, findings or key figures in archaeology. Example: "Which British archaeologist discovered the tomb of Tutankhamun in 1922?".

**#Subject::History::Military-History-And-Military-Structure-And-Functioning**
This tag applies when the question focuses on the history of warfare, armed forces, military strategies and tactics, specific battles (viewed historically), military technology, ranks, famous commanders, or the organization and structure of armies/navies/air forces. Example: "What was the name of the military strategy used by Germany in the early phases of World War II, characterized by fast, overwhelming attacks?".

**#Subject::History::Wars-And-Conflicts**
This tag applies when the question specifically asks about particular wars, armed conflicts, revolutions (viewed as conflicts), or civil wars, focusing on their causes, course, key events, outcomes, or participants. Example: "The Peloponnesian War was fought between which two ancient Greek city-states?".

**#Subject::History::Disasters-Or-Tragedies**
This tag applies when the question concerns significant historical events involving widespread human suffering, loss of life, or destruction, whether natural (earthquakes, floods, pandemics) or man-made (industrial accidents, famines caused by policy, shipwrecks like the Titanic). Example: "The Chernobyl disaster involved an accident at what type of facility?".

**#Subject::History::Empires-And-Civilisations**
This tag applies when the question relates to large-scale political entities (empires like the Roman, British, Ottoman, Mongol) or broad cultural and social entities (civilizations like Ancient Egypt, Mesopotamia, Indus Valley), focusing on their rise, characteristics, expansion, rulers, achievements, and decline. Example: "Which empire, ruling large parts of India from the 16th to the 19th century, was known for its Mughal architecture?".

**#Subject::Natural-World**
This tag applies broadly to questions concerning the physical world and its phenomena, encompassing life sciences, physical sciences, earth sciences, and mathematics.

**#Subject::Natural-World::Physics**
This tag applies when the question relates to the fundamental science of matter, energy, motion, force, space, and time. Includes classical mechanics, thermodynamics, electromagnetism, relativity, quantum mechanics, famous physicists (Newton, Einstein, Bohr), or physical laws and principles. Example: "What is Einstein's famous equation relating mass and energy?".

**#Subject::Natural-World::Units-And-Metrology**
This tag applies when the question specifically concerns units of measurement (SI units, imperial units), systems of measurement, scientific instruments used for measuring, constants with specific units, or the science of measurement itself (metrology). Example: "What is the SI unit for electric current?".

**#Subject::Natural-World::Chemistry-And-Chemicals**
This tag applies when the question relates to the study of matter and its properties, especially the composition, structure, properties, and reactions of substances. Includes chemical bonding, reactions, acids/bases, organic/inorganic chemistry, famous chemists, or specific chemical compounds and processes. Example: "What is the chemical formula for table salt?".

**#Subject::Natural-World::Elements**
This tag applies when the question specifically focuses on chemical elements, the periodic table, properties of specific elements (like gold, oxygen, carbon), isotopes, discovery of elements, or their symbols. Example: "What chemical element has the symbol 'Fe' and is essential for carrying oxygen in human blood?".

**#Subject::Natural-World::Flora-And-Fauna**
This tag applies when the question concerns plants (flora) and animals (fauna), including biology, zoology, botany, classification (taxonomy), specific species, habitats, ecosystems, animal behavior, or plant physiology. Example: "What is the largest land animal currently living on Earth?".

**#Subject::Natural-World::Earth-And-Environmental-Sciences**
This tag applies when the question relates to the sciences dealing with the planet Earth, including geology (rocks, minerals, plate tectonics), meteorology (weather, climate), oceanography (oceans), paleontology (fossils), and environmental science (interactions between physical, chemical, and biological components of the environment, pollution). Example: "What type of rock is formed from cooled magma or lava?".

**#Subject::Natural-World::Conservation**
This tag applies when the question concerns the protection, preservation, management, or restoration of natural environments and ecological communities, including endangered species, biodiversity, national parks, conservation efforts, sustainability, or environmental protection movements and organizations. Example: "What international organization maintains the 'Red List' of threatened species?".

**#Subject::Natural-World::Mathematics-And-Related-Fields**
This tag applies when the question relates to the abstract science of number, quantity, and space, including arithmetic, algebra, geometry, calculus, statistics, probability, logic (as a formal system), famous mathematicians, or mathematical theorems and problems. Example: "What is the value of Pi (π) to two decimal places?".

**#Subject::Natural-World::Space-And-Space-Exploration**
This tag applies when the question concerns celestial objects (stars, planets, galaxies, comets, asteroids), astronomy, cosmology (origin and evolution of the universe), space exploration missions (Apollo, Voyager), spacecraft, astronauts, telescopes, or astronomical phenomena (eclipses, black holes). Example: "Which planet is known as the 'Red Planet'?".

**#Subject::Health-And-Medicine**
This tag applies broadly to questions concerning the state of physical, mental, and social well-being, the science and practice of diagnosing, treating, and preventing disease, and the functioning of the human body.

**#Subject::Health-And-Medicine::Human-Body-Psychology**
This tag applies when the question relates to the structure (anatomy) and function (physiology) of the human body, its systems (nervous, circulatory, etc.), or the scientific study of the mind and behavior (psychology), including mental processes, emotions, cognition, and psychological theories or disorders. Example: "Which organ in the human body produces insulin?". Or "In psychology, what term describes learning by association, as demonstrated by Pavlov's dogs?".

**#Subject::Health-And-Medicine::Diseases-And-Pathologies**
This tag applies when the question concerns specific illnesses, diseases, disorders, medical conditions, their symptoms, causes (pathogens like bacteria, viruses), diagnosis, or pathology (the study of disease). Example: "Which disease is caused by the human immunodeficiency virus (HIV)?".

**#Subject::Health-And-Medicine::Disease-Outbreaks**
This tag applies when the question specifically focuses on epidemics, pandemics, or significant outbreaks of infectious diseases, including their history, spread (epidemiology), public health responses, or specific historical outbreaks (like the Spanish Flu, Black Death, recent pandemics). Example: "What disease caused a major pandemic starting in 1918, often called the 'Spanish Flu'?".

**#Subject::Health-And-Medicine::Drugs-And-Medicines**
This tag applies when the question relates to pharmaceutical drugs, medicines, vaccines, treatments, pharmacology (how drugs affect the body), drug discovery, famous medical drugs (like penicillin, aspirin), or recreational drugs discussed in a medical/health context. Example: "Which scientist is credited with the discovery of penicillin?".

**#Subject::Health-And-Medicine::Medical-Specialities**
This tag applies when the question concerns specific branches of medicine or healthcare professions, such as cardiology (heart), oncology (cancer), pediatrics (children), surgery, nursing, dentistry, radiology, or psychiatry. Example: "What medical specialty deals with the diagnosis and treatment of cancer?".

**#Subject::Health-And-Medicine::Alternative-Medicine**
This tag applies when the question relates to health treatments and therapies that are not part of standard Western medical practice, such as acupuncture, homeopathy, naturopathy, chiropractic, herbal medicine, or traditional medicine systems (like Ayurveda, Traditional Chinese Medicine). Example: "What traditional Chinese medicine practice involves inserting thin needles into specific points on the body?".

**#Subject::Technology**
This tag applies broadly to questions concerning the application of scientific knowledge for practical purposes, especially in industry, encompassing machinery, tools, systems, techniques, and inventions.

**#Subject::Technology::Information-Technology**
This tag applies when the question relates to the use of computers, storage, networking, and other physical devices and infrastructure to create, process, store, secure, and exchange electronic data. Includes internet infrastructure, telecommunications, data management, cybersecurity, and IT concepts. Example: "What does the acronym 'URL' stand for in the context of the internet?".

**#Subject::Technology::Computers-And-Softwares**
This tag applies when the question focuses specifically on computer hardware (CPUs, memory, storage devices), software (operating systems like Windows/MacOS/Linux, applications like Word/Excel), programming languages (Python, Java, C++), algorithms, data structures, or the history of computing. Example: "Which company developed the Windows operating system?".

**#Subject::Technology::As-Business**
This tag applies when the question examines technology from a commercial perspective, focusing on technology companies (like Apple, Google, Microsoft), the business of software and hardware, tech startups, the economic impact of technology, or intellectual property in tech (patents). (Overlap with Business/Industry). Example: "Which two individuals co-founded Apple Inc.?".

**#Subject::Technology::Inventions**
This tag applies when the question focuses on specific inventions, the process of inventing, famous inventors (like Edison, Bell, Tesla), patents, or the historical development of key technological devices. Example: "Who is credited with inventing the telephone?".

**#Subject::Technology::Discoveries-And-Breakthroughs**
This tag applies when the question highlights significant scientific or technological discoveries, advancements, or breakthroughs that led to new understanding or capabilities, often bridging science and technology. Example: "The discovery of the structure of what molecule by Watson and Crick was a major breakthrough in biology and genetics?".

**#Subject::Technology::Everyday-Tools-Items-Or-Objects-We-Use**
This tag applies when the question concerns common tools, implements, appliances, or objects used in daily life, focusing on their function, history, design, or the technology behind them (e.g., zippers, Velcro, microwaves, ballpoint pens). Example: "What simple fastening device, inspired by burrs sticking to dog fur, was invented by George de Mestral?".

**#Subject::Food-And-Drink**
This tag applies broadly to questions concerning substances consumed for nutrition or pleasure, including their preparation, cultural significance, production, and related industries.

**#Subject::Food-And-Drink::Food-items-and-cuisines**
This tag applies when the question focuses on specific food dishes, ingredients, cooking methods, types of cuisine (Italian, Japanese, Mexican), famous chefs, restaurants, culinary history, or dietary practices. Example: "What is the main ingredient in traditional guacamole?".

**#Subject::Food-And-Drink::Beverages-Drinks-And-associated-places**
This tag applies when the question concerns drinks, both alcoholic (wine, beer, spirits) and non-alcoholic (coffee, tea, soft drinks), including their production (brewing, vinting), types, brands, history, associated establishments (pubs, cafes, wineries), or cultural practices related to drinking. Example: "Which country is famous for originating tequila?".

**#Subject::Food-And-Drink::Agriculture-And-Natural-Products**
This tag applies when the question relates to the cultivation of crops, raising of livestock, farming practices, types of produce, food production systems, fisheries, forestry (for food/drink products like maple syrup), or natural unprocessed food items. Example: "What type of grain is the primary ingredient in risotto?".

**#Subject::Fashion-And-Costume**
This tag applies when the question relates to clothing styles, trends, fashion design, famous designers, models, fashion houses, accessories, cosmetics, historical costume, or the social and cultural aspects of dress. Example: "Which French fashion designer is famous for the 'little black dress' and No. 5 perfume?".

**#Subject::Travel-And-Tourism**
This tag applies when the question concerns the activity or industry related to traveling for pleasure or business, including destinations, modes of travel (in the context of tourism), types of tourism (ecotourism, adventure tourism), accommodation (hotels), travel agencies, guidebooks, or famous travel writers/experiences. Example: "What term describes tourism directed towards exotic, often threatened, natural environments, intended to support conservation efforts?".

**#Subject::Lifestyle**
This tag applies broadly to questions about the ways in which individuals, groups, or societies live, encompassing habits, attitudes, possessions, and social orientations.

**#Subject::Lifestyle::Luxury**
This tag applies when the question concerns goods, services, and lifestyles associated with great expense, comfort, and high quality, including luxury brands (in fashion, cars, watches), high-end travel, fine dining (as a lifestyle aspect), or symbols of wealth and status. Example: "Which Swiss brand is famous for its luxury watches like the Submariner and Daytona?".

**#Subject::Lifestyle::Alternative-Lifestyles**
This tag applies when the question relates to ways of living that deviate significantly from mainstream societal norms, such as communal living, off-grid living, minimalism, specific dietary lifestyles (veganism as a lifestyle choice beyond just diet), or participation in certain subcultures defining one's way of life. Example: "What lifestyle philosophy emphasizes living with only the essential items one needs?".

**#Subject::Lifestyle::Leisure-And-Recreation**
This tag applies when the question concerns activities pursued during free time for enjoyment, relaxation, or personal fulfillment, including hobbies (see also Hobbies), entertainment (passive consumption like watching movies/TV for leisure), socializing, or recreational activities not classified as sports or games. Example: "What is the general term for activities undertaken for enjoyment during one's free time?".

**#Subject::Lifestyle::Hobbies-And-Pastimes**
This tag applies when the question focuses on specific activities undertaken regularly in leisure time for pleasure or relaxation, such as collecting (stamps, coins), model building, gardening, birdwatching, amateur radio, crafting (knitting, pottery as a hobby), or photography (as a hobby). Example: "What is the hobby of collecting and studying postage stamps called?".

**#Subject::Lifestyle::Daily-Life-Or-Home-Related**
This tag applies when the question concerns everyday routines, domestic activities, home management, common household objects or practices, family life, or the mundane aspects of living in a particular time or place. Example: "Before refrigerators, what common structure was used to keep food cool using ice?".

**#Subject::Finance**
This tag applies broadly to questions concerning the management of money, credit, investments, and assets, including financial systems, markets, and institutions.

**#Subject::Finance::Banking**
This tag applies when the question relates specifically to the business of banking, including types of banks (commercial, investment), central banks (like the Federal Reserve, Bank of England), banking operations (loans, deposits), financial regulation related to banks, or historical banking events. Example: "What is the central bank of the United States called?".

**#Subject::Finance::Money-And-Currency**
This tag applies when the question focuses on money itself, including specific currencies (Dollar, Euro, Yen), exchange rates, history of money (barter, coinage), inflation/deflation, monetary policy (controlled by central banks), or cryptocurrencies (like Bitcoin). Example: "What is the official currency of the member states of the Eurozone?".

**#Subject::Finance::Financial-Instruments**
This tag applies when the question concerns specific tools or contracts used for investment or managing financial risk, such as stocks (shares), bonds, derivatives (options, futures), mutual funds, ETFs, or insurance policies viewed as financial products. Example: "What type of financial instrument represents ownership in a corporation?".

**#Subject::Finance::Economics**
This tag applies when the question relates to the broader social science concerned with the production, distribution, and consumption of goods and services, including economic theories (Keynesian, neoclassical), concepts (supply and demand, GDP, unemployment), economic systems (capitalism, socialism), famous economists (Adam Smith, Karl Marx), or economic history. Example: "What economic principle states that, all else being equal, as the price of a good increases, the quantity demanded will decrease?".

**#Subject::Finance::Anything-else-related-to-finance**
This tag applies to financial topics not covered by the specific categories above, potentially including personal finance (budgeting, saving), corporate finance (company valuation, investment decisions), public finance (government spending, taxation), financial accounting, or specific financial crises or events.

**#Subject::Marketing**
This tag applies broadly to questions about the activities a company undertakes to promote the buying or selling of a product or service, including market research, advertising, branding, and sales strategies.

**#Subject::Marketing::Advertisements-And-Ad-Campaigns**
This tag applies when the question focuses specifically on advertisements (in print, TV, radio, online), advertising campaigns, famous slogans, advertising agencies, techniques used in advertising (persuasion, appeals), or the history of advertising. Example: "Which fast-food chain used the advertising slogan 'Have It Your Way'?".

**#Subject::Marketing::Branding**
This tag applies when the question concerns the process of creating a unique name, design, symbol, or combination thereof for a product or company to distinguish it in the marketplace. Includes brand identity, brand strategy, logos, brand names, brand loyalty, or rebranding efforts. Example: "What term describes the distinctive graphical symbol or emblem commonly used to identify a company or product?".

**#Subject::Business**
This tag applies broadly to questions about commercial, industrial, or professional activities involving the exchange of goods or services for profit. It covers company operations, management, strategy, and the overall business environment.

**#Subject::Business::Entrepreneurship-And-Startups**
This tag applies when the question relates to the process of designing, launching, and running a new business, including famous entrepreneurs, startup companies, venture capital, innovation in business, or concepts like business incubators. Example: "What term describes an individual who organizes and operates a business or businesses, taking on greater than normal financial risks?".

**#Subject::Business::Corporate-History-And-Trivia**
This tag applies when the question concerns the history, evolution, founders, key milestones, mergers and acquisitions, or interesting facts (trivia) about specific corporations or companies. Example: "Which technology company originally started as a search engine project by Larry Page and Sergey Brin at Stanford University?".

**#Subject::Business::Trade-And-Merchantry**
This tag applies when the question focuses on the act or business of buying and selling goods, especially on a large scale or internationally. Includes historical trade routes, merchant activities, import/export, trade organizations (like WTO), or concepts like balance of trade. Example: "What historical trade route connected the East and West, facilitating the exchange of silk, spices, and ideas?".

**#Subject::Industry**
This tag applies broadly to questions about specific sectors of economic activity concerned with the processing of raw materials, manufacturing of goods, or provision of services. It focuses on the nature of different industries.

**#Subject::Industry::Any-Natural-Resource-Extraction-And-Refining**
This tag applies when the question relates to industries involved in extracting natural resources from the earth, such as mining (coal, metals, minerals), oil and gas extraction, quarrying, logging, or fishing, as well as the initial processing or refining of these resources (e.g., oil refineries, ore smelting). Example: "What organization, often meeting in Vienna, coordinates petroleum policies among major oil-exporting countries?".

**#Subject::Industry::Manufacturing**
This tag applies when the question concerns industries involved in making goods or products from raw materials by manual labor or machinery, including automotive manufacturing, electronics production, textile manufacturing, chemical production, food processing, or heavy industry. Example: "What manufacturing process, pioneered by Henry Ford, involves assembling components sequentially along a moving line?".

**#Subject::Industry::Construction-And-Materials**
This tag applies when the question relates to the industry involved in building structures (buildings, infrastructure) or the production and supply of materials used in construction (cement, steel, glass, lumber). Example: "What composite material, consisting of cement, aggregate, and water, is a fundamental material in modern construction?".

**#Subject::Industry::Industrial-Or-Corporate-Goods-And-Services**
This tag applies when the question concerns businesses that primarily sell goods or services to other businesses (B2B), rather than directly to consumers. This includes manufacturers of industrial machinery, providers of corporate consulting services, enterprise software companies, or wholesale suppliers. Example: "What type of consulting focuses on helping organizations improve their performance, primarily through the analysis of existing business problems?".

**#Subject::Industry::Trade**
This tag applies when the question focuses on the industry sector involved in the buying and selling of goods, overlapping with Business::Trade but viewed from an industry classification perspective (e.g., the wholesale or retail trade sector).

**#Subject::Industry::Transport-and-Logistics**
This tag applies when the question concerns the industry sector focused on providing transportation services (airlines, shipping companies, trucking firms, railways) or logistics and supply chain management services. (Overlap with Transport::Trade-And-Logistics). Example: "Which American company is a major global provider of courier delivery and logistics services, known for its overnight shipping?".

**#Subject::Industry::Retail-And-Wholesale**
This tag applies when the question relates to the industry involved in selling goods directly to consumers (retail) or selling goods in large quantities to retailers or other businesses (wholesale). Includes department stores, supermarkets, e-commerce retailers, or wholesale distributors. Example: "Which American multinational corporation operates a chain of hypermarkets, discount department stores, and grocery stores?".

**#Subject::Industry::Consumer-Staples-Goods-And-Services**
This tag applies when the question concerns industries producing or selling essential goods and services that consumers buy regularly, regardless of economic conditions, such as food and beverage companies, household product manufacturers, or tobacco companies. Example: "Which Swiss multinational food and drink processing conglomerate is one of the largest food companies in the world?".

**#Subject::Industry::Arts-And-Media-As-Business**
This tag applies when the question examines the arts, entertainment, and media sectors from an industrial or business perspective, including film studios, record labels, publishing houses, broadcasting companies, or the economics of the art market. Example: "What are the 'Big Three' major record labels in the global music industry?".

**#Subject::Industry::Personal-Services-Like-Healthcare-Education-and-Others**
This tag applies when the question concerns industries providing services directly to individuals, such as healthcare providers (hospitals, clinics), educational institutions (schools, universities viewed as service providers), personal care services (salons, spas), or hospitality (hotels, restaurants viewed as service industries). Example: "What industry sector includes businesses that provide accommodation, food, and beverage services to travelers and guests?".

**#Subject::Industry::Utilities-And-Commodities**
This tag applies when the question relates to industries providing essential public services like electricity, natural gas, and water supply (utilities), or industries dealing with basic goods or raw materials traded in bulk, such as agricultural products, metals, or energy (commodities trading). Example: "What type of company typically provides essential services like electricity or water to the public?".

**#Subject::Industry::Information-Technology-Communication-And-Media-Services**
This tag applies when the question concerns the industry sector encompassing software development, IT services, telecommunications providers (phone, internet), data processing, and media services (distinct from content creation, focusing on service provision). Example: "What industry includes companies that provide internet access to consumers and businesses?".

**#Subject::Industry::Capital-Goods-Including-Equipment**
This tag applies when the question relates to industries that produce goods used in the production of other goods or services, such as machinery, manufacturing equipment, construction equipment, commercial aircraft, or industrial robots. Example: "Which American company is a major manufacturer of construction and mining equipment, diesel engines, and industrial gas turbines?".

**#Modifiers::Related-To::Person**
This tag applies when the central focus or answer of the question is a specific individual (male or unspecified gender). Example: "Who painted the Mona Lisa?" (Answer: Leonardo da Vinci, a person).

**#Modifiers::Related-To::Female-Person-Or-Women**
This tag applies when the central focus or answer of the question is specifically a female individual or relates directly to women as a group. Example: "Who was the first woman to win a Nobel Prize?" (Answer: Marie Curie, a female person).

**#Modifiers::Related-To::Children-And-Young-People**
This tag applies when the question specifically pertains to children, adolescents, or youth culture, topics like childhood development, children's literature, youth movements, or issues primarily affecting young people. Example: "Which fictional school does Harry Potter attend?".

**#Modifiers::Related-To::Any-Organization**
This tag applies when the central focus or answer of the question is a specific organization, institution, company, association, government body, or group with a formal structure. Example: "Which international organization aims to maintain international peace and security?" (Answer: The United Nations, an organization).

**#Modifiers::Related-To::A-Group-Of-People-With-Something-Common**
This tag applies when the question pertains to a collective group of people defined by a shared characteristic, identity, experience, or affiliation, but not necessarily a formal organization (e.g., an ethnic group, a profession, adherents of a belief, members of a subculture). Example: "What term refers to the indigenous people of Australia?".

**#Modifiers::Related-To::Idea**
This tag applies when the question's core subject or answer is an abstract concept, thought, theory, belief, philosophy, or mental construct. Example: "What is the philosophical concept suggesting that knowledge comes primarily from sensory experience?".

**#Modifiers::Related-To::Breakthrough**
This tag applies when the question highlights a significant advance, discovery, or innovation that represents a major step forward in a particular field. Example: "The development of penicillin is considered a major ______ in medicine?".

**#Modifiers::Related-To::Mental-Construct**
This tag applies when the question deals with concepts that exist primarily in the mind or are defined by human thought and agreement, such as social constructs, theoretical models, fictional entities, or classifications. Example: "Is the concept of 'race' considered a biological reality or a social construct by most anthropologists?".

**#Modifiers::Related-To::Moment**
This tag applies when the question focuses on a specific point in time, a brief event, or a critical juncture that had significant consequences or is remembered for its distinctiveness. Example: "In which year did Neil Armstrong first walk on the Moon?".

**#Modifiers::Related-To::Decision-or-Incident**
This tag applies when the question revolves around a specific choice, action, policy decision, accident, or notable occurrence that had particular repercussions or significance. Example: "What specific incident in Sarajevo triggered the start of World War I?".

**#Modifiers::Related-To::Consequence**
This tag applies when the question explicitly asks about the result, effect, outcome, or impact of a particular event, action, discovery, or phenomenon. Example: "What was a major economic consequence of the Black Death in Europe?".

**#Modifiers::Related-To::Change-or-Old-Version-Of-Something**
This tag applies when the question deals with transformation, evolution, historical development, or contrasts a current state with a previous version of something (e.g., technology, names, borders, ideas). Example: "What was the former name of the city now known as Istanbul?".

**#Modifiers::Related-To::Place-Location-Construction-Or-Formation**
This tag applies when the answer or core subject is a specific geographical place, location, building, structure, or relates to its creation, construction, or natural formation. Example: "Where is the Eiffel Tower located?".

**#Modifiers::Related-To::Award-Recogniton-Or-Achievement**
This tag applies when the question pertains to prizes, awards, honors, titles, formal recognition, or significant accomplishments in any field. Example: "Which award is considered the highest honor in the film industry?".

**#Modifiers::Related-To::Record-Superlative-Or-Distinction**
This tag applies when the question asks about extremes – the biggest, smallest, fastest, slowest, oldest, newest, first, last, or most/least of something, highlighting a record or superlative status. Example: "What is the highest mountain in the world?".

**#Modifiers::Related-To::Mystery-or-Unexplained-Thing-Or-Coincidence**
This tag applies when the question concerns phenomena, events, or objects that are puzzling, enigmatic, not fully understood, or involve striking coincidences. Example: "What is the name given to the mysterious region in the North Atlantic Ocean where ships and planes are said to have disappeared?".

**#Modifiers::Related-To::Event-or-Process**
This tag applies when the question's focus is on a specific happening, occurrence, festival, ceremony, or a series of actions or steps taken to achieve a particular end (a process). Example: "What annual film festival is held in Cannes, France?". Or "What is the biological process by which plants convert light energy into chemical energy?".

**#Modifiers::Related-To::Practice-of-something**
This tag applies when the question relates to the actual application, exercise, custom, or habitual performance of an activity, skill, tradition, or belief. Example: "What is the Japanese practice of flower arranging called?".

**#Modifiers::Related-To::History-Of-Something**
This tag applies when the question specifically asks about the origin, development, evolution, or past sequence of events related to a particular subject (person, place, thing, idea, practice). Example: "What is the history of the internet?".

**#Modifiers::Related-To::Technique-Or-How-It-Is-Made-Or-Done**
This tag applies when the question asks about the specific method, skill, procedure, or way something is created, performed, or accomplished. Example: "What painting technique involves applying paint in small dots?".

**#Modifiers::Related-To::Useful-or-Practical-Object**
This tag applies when the answer or subject is a tangible item designed for a specific function or practical use, such as a tool, utensil, appliance, or everyday device. Example: "What handheld device is commonly used for making calculations?".

**#Modifiers::Related-To::Equipment**
This tag applies when the question concerns sets of tools, machinery, apparatus, or items needed for a particular purpose, activity, or profession, often more complex or specialized than simple tools. Example: "What piece of laboratory equipment is used to measure the volume of liquids accurately?".

**#Modifiers::Related-To::Rules**
This tag applies when the question asks about specific regulations, principles, instructions, or guidelines governing conduct, procedure, or the way a game or activity is played. Example: "In chess, what is the rule that prevents a player from making any legal move?".

**#Modifiers::Related-To::Laws**
This tag applies when the question pertains to specific statutes, legal principles, legislation, or systems of rules enforced by governmental authority. (More formal than 'Rules'). Example: "What US law prohibits discrimination based on race, color, religion, sex, or national origin?".

**#Modifiers::Related-To::Norms-Traditions-or-Etiquette**
This tag applies when the question concerns established social behaviors, customs, traditions, or codes of polite conduct accepted within a particular society or group. Example: "In many Western cultures, what is the traditional etiquette regarding which hand to use for a fork when cutting food with a knife?".

**#Modifiers::Worth-Asking-Because::Has-Some-Iconic-Or-Special-Status**
This tag applies when the subject of the question is widely recognized as representative, symbolic, or embodying the essential characteristics of something, giving it a special, iconic status beyond mere fame. Example: The Eiffel Tower as an icon of Paris, or the VW Beetle as an iconic car design.

**#Modifiers::Worth-Asking-Because::Famous**
This tag applies when the subject of the question (person, place, event, thing) is widely known or recognized by many people, making it a suitable topic for general knowledge or trivia. Example: Asking about Albert Einstein or World War II.

**#Modifiers::Worth-Asking-Because::Has-An-Inspiration-Or-Derivation-From-Something-Else**
This tag applies when the question highlights an interesting connection where the subject was inspired by, derived from, or based on another existing work, idea, event, or object, making the link itself notable. Example: West Side Story being inspired by Romeo and Juliet.

**#Modifiers::Worth-Asking-Because::Is-Unique-Rare-Special-Of-Exceptional-In-Some-Way**
This tag applies when the subject of the question stands out due to its uniqueness, rarity, exceptional quality, unusual characteristics, or singular nature, making it inherently interesting. Example: Asking about the Komodo dragon (unique location/size) or a specific scientific anomaly.
"""

DEFAULT_WORKFLOW_EXTRACTION_PROMPT = "TO_BE_INSERTED_LATER" # Deprecated? Replaced by visual/book specific ones? Let's keep for now but tie to visual
DEFAULT_WORKFLOW_TSV_PROMPT = "TO_BE_INSERTED_LATER" # Likely deprecated if P2 step 3/4 handle it.
SECOND_PASS_TAGGING = """You are an expert quiz question classifier. Your task is to analyze quiz question and answer pairs and generate relevant tags for each question from a predefined list of categories.

Instructions:

1. Analyze each quiz question and answer pair provided below.
2. For each question, select relevant tags from the provided "Reference Document" categories (implicitly understood to be the list you provided previously).
3. Output ONLY the tags for each question as a space-separated list.
4. Structure your response STRICTLY as a numbered list, with each line corresponding to an input item.  Begin each line with the item number in square brackets, followed by the space-separated tags.  *Do not include any text other than the item number and the tags.*

**Example Output Format:**

[1] tag1 tag2 tag3
[2] tag4 tag5
[3] tag6 tag7 tag8 tag9
... and so on for each item in the batch.

**Reference Document:** You HAVE to pick one category from between the {} flower brackets. Do NOT wrap the tags in flower brackets, just pick from between the brackets. **PICK ALL THE TAGS THAT APPLY**
For each question you will determine

#Subject:: Main subject of the question from the provided list.

#Modifiers::Related-To:: What concept or entity or aspect it is related to, even tangentially

#Modifiers::Worth-Asking-Because:: Reason why the question is worth asking

Reference Document: These categories include, and are limited to the following, stick to the ones from this list:

Subject
Make sure that at least one tag from the following set is chosen.
{
#Subject::Finance
#Subject::Finance::Banking
#Subject::Finance::Money-And-Currency
#Subject::Finance::Financial-Instruments
#Subject::Finance::Economics
#Subject::Finance::Anything-else-related-to-finance

#Subject::Marketing
#Subject::Marketing::Advertisements-And-Ad-Campaigns
#Subject::Marketing::Branding

#Subject::Business
#Subject::Business::Entrepreneurship-And-Startups
#Subject::Business::Corporate-History-And-Trivia
#Subject::Business::Trade-And-Merchantry

#Subject::Industry
#Subject::Industry::Any-Natural-Resource-Extraction-And-Refining
#Subject::Industry::Manufacturing
#Subject::Industry::Construction-And-Materials
#Subject::Industry::Industrial-Or-Corporate-Goods-And-Services
#Subject::Industry::Trade
#Subject::Industry::Transport-and-Logistics
#Subject::Industry::Retail-And-Wholesale
#Subject::Industry::Consumer-Staples-Goods-And-Services
#Subject::Industry::Arts-And-Media-As-Business
#Subject::Industry::Personal-Services-Like-Healthcare-Education-and-Others
#Subject::Industry::Utilities-And-Commodities
#Subject::Industry::Information-Technology-Communication-And-Media-Services
#Subject::Industry::Capital-Goods-Including-Equipment
}

#Modifiers
{
#Modifiers::Related-To::Person
#Modifiers::Related-To::Female-Person-Or-Women
#Modifiers::Related-To::Children-And-Young-People
#Modifiers::Related-To::Any-Organization
#Modifiers::Related-To::A-Group-Of-People-With-Something-Common
#Modifiers::Related-To::Idea
#Modifiers::Related-To::Breakthrough
#Modifiers::Related-To::Mental-Construct
#Modifiers::Related-To::Moment
#Modifiers::Related-To::Decision-or-Incident
#Modifiers::Related-To::Consequence
#Modifiers::Related-To::Change-or-Old-Version-Of-Something
#Modifiers::Related-To::Place-Location-Construction-Or-Formation
#Modifiers::Related-To::Award-Recogniton-Or-Achievement
#Modifiers::Related-To::Record-Superlative-Or-Distinction
#Modifiers::Related-To::Mystery-or-Unexplained-Thing-Or-Coincidence
#Modifiers::Related-To::Event-or-Process
#Modifiers::Related-To::Practice-of-something
#Modifiers::Related-To::History-Of-Something
#Modifiers::Related-To::Technique-Or-How-It-Is-Made-Or-Done
#Modifiers::Related-To::Useful-or-Practical-Object
#Modifiers::Related-To::Equipment
#Modifiers::Related-To::Rules
#Modifiers::Related-To::Laws
#Modifiers::Related-To::Norms-Traditions-or-Etiquette

#Modifiers::Worth-Asking-Because::Has-Some-Iconic-Or-Special-Status
#Modifiers::Worth-Asking-Because::Famous
#Modifiers::Worth-Asking-Because::Has-An-Inspiration-Or-Derivation-From-Something-Else
#Modifiers::Worth-Asking-Because::Is-Unique-Rare-Special-Of-Exceptional-In-Some-Way
}

Here are mini-essays describing the aspects covered by each tag:

**#Subject::Finance**
This tag applies broadly to questions concerning the management of money, credit, investments, and assets, including financial systems, markets, and institutions.

**#Subject::Finance::Banking**
This tag applies when the question relates specifically to the business of banking, including types of banks (commercial, investment), central banks (like the Federal Reserve, Bank of England), banking operations (loans, deposits), financial regulation related to banks, or historical banking events. Example: "What is the central bank of the United States called?".

**#Subject::Finance::Money-And-Currency**
This tag applies when the question focuses on money itself, including specific currencies (Dollar, Euro, Yen), exchange rates, history of money (barter, coinage), inflation/deflation, monetary policy (controlled by central banks), or cryptocurrencies (like Bitcoin). Example: "What is the official currency of the member states of the Eurozone?".

**#Subject::Finance::Financial-Instruments**
This tag applies when the question concerns specific tools or contracts used for investment or managing financial risk, such as stocks (shares), bonds, derivatives (options, futures), mutual funds, ETFs, or insurance policies viewed as financial products. Example: "What type of financial instrument represents ownership in a corporation?".

**#Subject::Finance::Economics**
This tag applies when the question relates to the broader social science concerned with the production, distribution, and consumption of goods and services, including economic theories (Keynesian, neoclassical), concepts (supply and demand, GDP, unemployment), economic systems (capitalism, socialism), famous economists (Adam Smith, Karl Marx), or economic history. Example: "What economic principle states that, all else being equal, as the price of a good increases, the quantity demanded will decrease?".

**#Subject::Finance::Anything-else-related-to-finance**
This tag applies to financial topics not covered by the specific categories above, potentially including personal finance (budgeting, saving), corporate finance (company valuation, investment decisions), public finance (government spending, taxation), financial accounting, or specific financial crises or events.

**#Subject::Marketing**
This tag applies broadly to questions about the activities a company undertakes to promote the buying or selling of a product or service, including market research, advertising, branding, and sales strategies.

**#Subject::Marketing::Advertisements-And-Ad-Campaigns**
This tag applies when the question focuses specifically on advertisements (in print, TV, radio, online), advertising campaigns, famous slogans, advertising agencies, techniques used in advertising (persuasion, appeals), or the history of advertising. Example: "Which fast-food chain used the advertising slogan 'Have It Your Way'?".

**#Subject::Marketing::Branding**
This tag applies when the question concerns the process of creating a unique name, design, symbol, or combination thereof for a product or company to distinguish it in the marketplace. Includes brand identity, brand strategy, logos, brand names, brand loyalty, or rebranding efforts. Example: "What term describes the distinctive graphical symbol or emblem commonly used to identify a company or product?".

**#Subject::Business**
This tag applies broadly to questions about commercial, industrial, or professional activities involving the exchange of goods or services for profit. It covers company operations, management, strategy, and the overall business environment.

**#Subject::Business::Entrepreneurship-And-Startups**
This tag applies when the question relates to the process of designing, launching, and running a new business, including famous entrepreneurs, startup companies, venture capital, innovation in business, or concepts like business incubators. Example: "What term describes an individual who organizes and operates a business or businesses, taking on greater than normal financial risks?".

**#Subject::Business::Corporate-History-And-Trivia**
This tag applies when the question concerns the history, evolution, founders, key milestones, mergers and acquisitions, or interesting facts (trivia) about specific corporations or companies. Example: "Which technology company originally started as a search engine project by Larry Page and Sergey Brin at Stanford University?".

**#Subject::Business::Trade-And-Merchantry**
This tag applies when the question focuses on the act or business of buying and selling goods, especially on a large scale or internationally. Includes historical trade routes, merchant activities, import/export, trade organizations (like WTO), or concepts like balance of trade. Example: "What historical trade route connected the East and West, facilitating the exchange of silk, spices, and ideas?".

**#Subject::Industry**
This tag applies broadly to questions about specific sectors of economic activity concerned with the processing of raw materials, manufacturing of goods, or provision of services. It focuses on the nature of different industries.

**#Subject::Industry::Any-Natural-Resource-Extraction-And-Refining**
This tag applies when the question relates to industries involved in extracting natural resources from the earth, such as mining (coal, metals, minerals), oil and gas extraction, quarrying, logging, or fishing, as well as the initial processing or refining of these resources (e.g., oil refineries, ore smelting). Example: "What organization, often meeting in Vienna, coordinates petroleum policies among major oil-exporting countries?".

**#Subject::Industry::Manufacturing**
This tag applies when the question concerns industries involved in making goods or products from raw materials by manual labor or machinery, including automotive manufacturing, electronics production, textile manufacturing, chemical production, food processing, or heavy industry. Example: "What manufacturing process, pioneered by Henry Ford, involves assembling components sequentially along a moving line?".

**#Subject::Industry::Construction-And-Materials**
This tag applies when the question relates to the industry involved in building structures (buildings, infrastructure) or the production and supply of materials used in construction (cement, steel, glass, lumber). Example: "What composite material, consisting of cement, aggregate, and water, is a fundamental material in modern construction?".

**#Subject::Industry::Industrial-Or-Corporate-Goods-And-Services**
This tag applies when the question concerns businesses that primarily sell goods or services to other businesses (B2B), rather than directly to consumers. This includes manufacturers of industrial machinery, providers of corporate consulting services, enterprise software companies, or wholesale suppliers. Example: "What type of consulting focuses on helping organizations improve their performance, primarily through the analysis of existing business problems?".

**#Subject::Industry::Trade**
This tag applies when the question focuses on the industry sector involved in the buying and selling of goods, overlapping with Business::Trade but viewed from an industry classification perspective (e.g., the wholesale or retail trade sector).

**#Subject::Industry::Transport-and-Logistics**
This tag applies when the question concerns the industry sector focused on providing transportation services (airlines, shipping companies, trucking firms, railways) or logistics and supply chain management services. (Overlap with Transport::Trade-And-Logistics). Example: "Which American company is a major global provider of courier delivery and logistics services, known for its overnight shipping?".

**#Subject::Industry::Retail-And-Wholesale**
This tag applies when the question relates to the industry involved in selling goods directly to consumers (retail) or selling goods in large quantities to retailers or other businesses (wholesale). Includes department stores, supermarkets, e-commerce retailers, or wholesale distributors. Example: "Which American multinational corporation operates a chain of hypermarkets, discount department stores, and grocery stores?".

**#Subject::Industry::Consumer-Staples-Goods-And-Services**
This tag applies when the question concerns industries producing or selling essential goods and services that consumers buy regularly, regardless of economic conditions, such as food and beverage companies, household product manufacturers, or tobacco companies. Example: "Which Swiss multinational food and drink processing conglomerate is one of the largest food companies in the world?".

**#Subject::Industry::Arts-And-Media-As-Business**
This tag applies when the question examines the arts, entertainment, and media sectors from an industrial or business perspective, including film studios, record labels, publishing houses, broadcasting companies, or the economics of the art market. Example: "What are the 'Big Three' major record labels in the global music industry?".

**#Subject::Industry::Personal-Services-Like-Healthcare-Education-and-Others**
This tag applies when the question concerns industries providing services directly to individuals, such as healthcare providers (hospitals, clinics), educational institutions (schools, universities viewed as service providers), personal care services (salons, spas), or hospitality (hotels, restaurants viewed as service industries). Example: "What industry sector includes businesses that provide accommodation, food, and beverage services to travelers and guests?".

**#Subject::Industry::Utilities-And-Commodities**
This tag applies when the question relates to industries providing essential public services like electricity, natural gas, and water supply (utilities), or industries dealing with basic goods or raw materials traded in bulk, such as agricultural products, metals, or energy (commodities trading). Example: "What type of company typically provides essential services like electricity or water to the public?".

**#Subject::Industry::Information-Technology-Communication-And-Media-Services**
This tag applies when the question concerns the industry sector encompassing software development, IT services, telecommunications providers (phone, internet), data processing, and media services (distinct from content creation, focusing on service provision). Example: "What industry includes companies that provide internet access to consumers and businesses?".

**#Subject::Industry::Capital-Goods-Including-Equipment**
This tag applies when the question relates to industries that produce goods used in the production of other goods or services, such as machinery, manufacturing equipment, construction equipment, commercial aircraft, or industrial robots. Example: "Which American company is a major manufacturer of construction and mining equipment, diesel engines, and industrial gas turbines?".

**#Modifiers::Related-To::Person**
This tag applies when the central focus or answer of the question is a specific individual (male or unspecified gender). Example: "Who painted the Mona Lisa?" (Answer: Leonardo da Vinci, a person).

**#Modifiers::Related-To::Female-Person-Or-Women**
This tag applies when the central focus or answer of the question is specifically a female individual or relates directly to women as a group. Example: "Who was the first woman to win a Nobel Prize?" (Answer: Marie Curie, a female person).

**#Modifiers::Related-To::Children-And-Young-People**
This tag applies when the question specifically pertains to children, adolescents, or youth culture, topics like childhood development, children's literature, youth movements, or issues primarily affecting young people. Example: "Which fictional school does Harry Potter attend?".

**#Modifiers::Related-To::Any-Organization**
This tag applies when the central focus or answer of the question is a specific organization, institution, company, association, government body, or group with a formal structure. Example: "Which international organization aims to maintain international peace and security?" (Answer: The United Nations, an organization).

**#Modifiers::Related-To::A-Group-Of-People-With-Something-Common**
This tag applies when the question pertains to a collective group of people defined by a shared characteristic, identity, experience, or affiliation, but not necessarily a formal organization (e.g., an ethnic group, a profession, adherents of a belief, members of a subculture). Example: "What term refers to the indigenous people of Australia?".

**#Modifiers::Related-To::Idea**
This tag applies when the question's core subject or answer is an abstract concept, thought, theory, belief, philosophy, or mental construct. Example: "What is the philosophical concept suggesting that knowledge comes primarily from sensory experience?".

**#Modifiers::Related-To::Breakthrough**
This tag applies when the question highlights a significant advance, discovery, or innovation that represents a major step forward in a particular field. Example: "The development of penicillin is considered a major ______ in medicine?".

**#Modifiers::Related-To::Mental-Construct**
This tag applies when the question deals with concepts that exist primarily in the mind or are defined by human thought and agreement, such as social constructs, theoretical models, fictional entities, or classifications. Example: "Is the concept of 'race' considered a biological reality or a social construct by most anthropologists?".

**#Modifiers::Related-To::Moment**
This tag applies when the question focuses on a specific point in time, a brief event, or a critical juncture that had significant consequences or is remembered for its distinctiveness. Example: "In which year did Neil Armstrong first walk on the Moon?".

**#Modifiers::Related-To::Decision-or-Incident**
This tag applies when the question revolves around a specific choice, action, policy decision, accident, or notable occurrence that had particular repercussions or significance. Example: "What specific incident in Sarajevo triggered the start of World War I?".

**#Modifiers::Related-To::Consequence**
This tag applies when the question explicitly asks about the result, effect, outcome, or impact of a particular event, action, discovery, or phenomenon. Example: "What was a major economic consequence of the Black Death in Europe?".

**#Modifiers::Related-To::Change-or-Old-Version-Of-Something**
This tag applies when the question deals with transformation, evolution, historical development, or contrasts a current state with a previous version of something (e.g., technology, names, borders, ideas). Example: "What was the former name of the city now known as Istanbul?".

**#Modifiers::Related-To::Place-Location-Construction-Or-Formation**
This tag applies when the answer or core subject is a specific geographical place, location, building, structure, or relates to its creation, construction, or natural formation. Example: "Where is the Eiffel Tower located?".

**#Modifiers::Related-To::Award-Recogniton-Or-Achievement**
This tag applies when the question pertains to prizes, awards, honors, titles, formal recognition, or significant accomplishments in any field. Example: "Which award is considered the highest honor in the film industry?".

**#Modifiers::Related-To::Record-Superlative-Or-Distinction**
This tag applies when the question asks about extremes – the biggest, smallest, fastest, slowest, oldest, newest, first, last, or most/least of something, highlighting a record or superlative status. Example: "What is the highest mountain in the world?".

**#Modifiers::Related-To::Mystery-or-Unexplained-Thing-Or-Coincidence**
This tag applies when the question concerns phenomena, events, or objects that are puzzling, enigmatic, not fully understood, or involve striking coincidences. Example: "What is the name given to the mysterious region in the North Atlantic Ocean where ships and planes are said to have disappeared?".

**#Modifiers::Related-To::Event-or-Process**
This tag applies when the question's focus is on a specific happening, occurrence, festival, ceremony, or a series of actions or steps taken to achieve a particular end (a process). Example: "What annual film festival is held in Cannes, France?". Or "What is the biological process by which plants convert light energy into chemical energy?".

**#Modifiers::Related-To::Practice-of-something**
This tag applies when the question relates to the actual application, exercise, custom, or habitual performance of an activity, skill, tradition, or belief. Example: "What is the Japanese practice of flower arranging called?".

**#Modifiers::Related-To::History-Of-Something**
This tag applies when the question specifically asks about the origin, development, evolution, or past sequence of events related to a particular subject (person, place, thing, idea, practice). Example: "What is the history of the internet?".

**#Modifiers::Related-To::Technique-Or-How-It-Is-Made-Or-Done**
This tag applies when the question asks about the specific method, skill, procedure, or way something is created, performed, or accomplished. Example: "What painting technique involves applying paint in small dots?".

**#Modifiers::Related-To::Useful-or-Practical-Object**
This tag applies when the answer or subject is a tangible item designed for a specific function or practical use, such as a tool, utensil, appliance, or everyday device. Example: "What handheld device is commonly used for making calculations?".

**#Modifiers::Related-To::Equipment**
This tag applies when the question concerns sets of tools, machinery, apparatus, or items needed for a particular purpose, activity, or profession, often more complex or specialized than simple tools. Example: "What piece of laboratory equipment is used to measure the volume of liquids accurately?".

**#Modifiers::Related-To::Rules**
This tag applies when the question asks about specific regulations, principles, instructions, or guidelines governing conduct, procedure, or the way a game or activity is played. Example: "In chess, what is the rule that prevents a player from making any legal move?".

**#Modifiers::Related-To::Laws**
This tag applies when the question pertains to specific statutes, legal principles, legislation, or systems of rules enforced by governmental authority. (More formal than 'Rules'). Example: "What US law prohibits discrimination based on race, color, religion, sex, or national origin?".

**#Modifiers::Related-To::Norms-Traditions-or-Etiquette**
This tag applies when the question concerns established social behaviors, customs, traditions, or codes of polite conduct accepted within a particular society or group. Example: "In many Western cultures, what is the traditional etiquette regarding which hand to use for a fork when cutting food with a knife?".

**#Modifiers::Worth-Asking-Because::Has-Some-Iconic-Or-Special-Status**
This tag applies when the subject of the question is widely recognized as representative, symbolic, or embodying the essential characteristics of something, giving it a special, iconic status beyond mere fame. Example: The Eiffel Tower as an icon of Paris, or the VW Beetle as an iconic car design.

**#Modifiers::Worth-Asking-Because::Famous**
This tag applies when the subject of the question (person, place, event, thing) is widely known or recognized by many people, making it a suitable topic for general knowledge or trivia. Example: Asking about Albert Einstein or World War II.

**#Modifiers::Worth-Asking-Because::Has-An-Inspiration-Or-Derivation-From-Something-Else**
This tag applies when the question highlights an interesting connection where the subject was inspired by, derived from, or based on another existing work, idea, event, or object, making the link itself notable. Example: West Side Story being inspired by Romeo and Juliet.

**#Modifiers::Worth-Asking-Because::Is-Unique-Rare-Special-Of-Exceptional-In-Some-Way**
This tag applies when the subject of the question stands out due to its uniqueness, rarity, exceptional quality, unusual characteristics, or singular nature, making it inherently interesting. Example: Asking about the Komodo dragon (unique location/size) or a specific scientific anomaly. """
