import { mockApi } from "../mockApi";
export class IncidentApiError extends Error { constructor(public code:string,message:string){super(message)} }
const base=import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";
const http={listIncidents:async()=>{const r=await fetch(base+"/incidents");if(!r.ok)throw new IncidentApiError("HTTP_ERROR","Incident request failed");return r.json()},getIncident:async(id:string)=>{const r=await fetch(base+"/incidents/"+id);if(r.status===404)return undefined;if(!r.ok)throw new IncidentApiError("HTTP_ERROR","Incident request failed");return r.json()}};
export const incidentApi=import.meta.env.VITE_API_MODE==="http"?http:{listIncidents:mockApi.listIncidents,getIncident:mockApi.getIncident};
