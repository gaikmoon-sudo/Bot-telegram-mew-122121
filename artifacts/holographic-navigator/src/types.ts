export type NodeKind='root'|'path'|'course'|'module'|'lesson';
export type TreeNode={id:string;title:string;description?:string;kind:NodeKind;parentId?:string;status?:string;color:string;children?:TreeNode[];meta?:Record<string,unknown>};
export type ApiPage<T>= {items:T[]; total?:number};
export type RawRow=Record<string,any>;
