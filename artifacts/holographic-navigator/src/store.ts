import {create} from 'zustand';
import {persist} from 'zustand/middleware';
import type {TreeNode} from './types';

type Store={root:TreeNode|null;selected:string;expanded:string[];mode:'3d'|'2d';query:string;setRoot:(root:TreeNode)=>void;select:(id:string)=>void;toggle:(id:string)=>void;setMode:(mode:'3d'|'2d')=>void;setQuery:(query:string)=>void;reset:()=>void};
export const useTreeStore=create<Store>()(persist((set)=>({root:null,selected:'root',expanded:['root'],mode:'3d',query:'',setRoot:(root)=>set({root}),select:(selected)=>set({selected,expanded:[...new Set([selected])]}),toggle:(id)=>set(s=>({expanded:s.expanded.includes(id)?s.expanded.filter(x=>x!==id):[...s.expanded,id]})),setMode:(mode)=>set({mode}),setQuery:(query)=>set({query}),reset:()=>set({selected:'root',expanded:['root'],query:''})}),{name:'telegram-academy-hologram-state'}));
