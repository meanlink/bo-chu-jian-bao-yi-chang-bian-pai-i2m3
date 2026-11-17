/** @typedef {{id:number,name:string,source:string,rows:number,checksum:string}} Dataset */
/** @typedef {{id:number,name:string,dataset_id:number,status:string,result:Object,approved:boolean,recalc_required:boolean,basis_revision:number,basis:Object}} AnalysisJob */
/** @typedef {{id:number,name:string,job_id:number,destination:string,next_run:number,enabled:boolean,basis_revision:number}} ReportSchedule */
/** @typedef {{id:number,name:string,channel:string,start_at:string,end_at:string,status:string,revision:number,version:number}} Maintenance */
export {};
