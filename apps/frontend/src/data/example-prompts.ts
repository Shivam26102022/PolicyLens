export interface ExamplePrompt {
  id: string;
  label: string;
  question: string;
  sourceId?: string;
}

export const examplePrompts: ExamplePrompt[] = [
  {
    id: "india-women-trainees",
    label: "India · Women's share of skills trainees",
    question:
      "In how many of India's five skills schemes did women represent close to half of trainees?",
    sourceId: "wb-india-skills-programs-2015",
  },
  {
    id: "malaysia-informal-employment-trend",
    label: "Malaysia · Informal employment rate, 2012–2022",
    question:
      "Using the study's proxy definition, what was Malaysia's informal-employment rate in 2012 and 2022?",
    sourceId: "wb-malaysia-informal-employment-2024",
  },
  {
    id: "indonesia-jobs-created-average",
    label: "Indonesia · Average jobs created",
    question:
      "How many jobs were created on average over the preceding three years, according to the Indonesia jobs study?",
    sourceId: "wb-indonesia-jobs-action-2018",
  },
  {
    id: "singapore-service-sector-share",
    label: "Singapore · Employment in services, 2007",
    question:
      "What share of Singapore's working population was employed in the service sector by 2007?",
    sourceId: "wb-singapore-workforce-development-2012",
  },
];
