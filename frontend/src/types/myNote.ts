export interface MyNote {
  idx: number;
  user_idx: number;
  note_name: string;
  create_date: string;
  origin_file: string;
  last_update: string;
}

export interface MyNoteDetail extends MyNote {
  content: string;
}
