import {maintenances} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {table} from '../components/common/table.js';
import {MaintenanceStatus} from '../constants/enums.js';
import {esc,fmt,date,notify} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';

const canWrite=()=>['admin','analyst'].includes(session.user.role);
const isAdmin=()=>session.user.role==='admin';

function statusChip(value){return '<span class="status '+esc(value)+'">'+esc(MaintenanceStatus[value]||value)+'</span>';}

function deductionTable(impact){
  if(!impact?.days?.length)return '<p class="empty">检修区间未覆盖任何播出日。</p>';
  const rows=impact.days.map(d=>({
    day:d.day,
    exempt:d.exempt_minutes,
    original:d.original_interruption===null||d.original_interruption===undefined?'—':d.original_interruption,
    net:d.net_interruption===null||d.net_interruption===undefined?'—':d.net_interruption,
  }));
  return table([{key:'day',label:'播出日'},{key:'exempt',label:'检修扣除(分钟)'},{key:'original',label:'扣除前原停播(分钟)'},{key:'net',label:'扣除后净停播(分钟)'}],rows)
    +'<p class="hint">跨午夜按自然日拆分，重叠时段只扣一次。合计扣除 '+esc(fmt(impact.total_minutes))+' 分钟；扣除后为负数的日期在执行重算时会被拒绝。</p>'
    +(impact.warnings?.length?impact.warnings.map(w=>'<p class="warning">'+esc(w)+'</p>').join(''):'');
}

function recordCard(item){
  const actions=[];
  if(item.status==='draft'){
    actions.push('<button class="button small" data-effective="'+item.id+'" '+(isAdmin()?'':'disabled')+'>生效并冻结版本</button>');
    actions.push('<button class="button small" data-edit="'+item.id+'" '+(canWrite()?'':'disabled')+'>补登修改</button>');
  }
  if(item.status==='effective'){
    actions.push('<button class="button small" data-revoke="'+item.id+'" '+(isAdmin()?'':'disabled')+'>撤销豁免</button>');
  }
  actions.push('<button class="text-button" data-impact="'+item.id+'">扣除前后与影响范围 ↗</button>');
  return '<article class="maintenance-item"><div><div class="maintenance-head"><strong>'+esc(item.name)+'</strong>'+statusChip(item.status)+'<span class="revision">v'+esc(item.version??'—')+' · 修订 '+esc(item.revision??'—')+'</span></div>'
    +'<p>'+esc(item.channel)+' · '+esc(item.start_at)+' → '+esc(item.end_at)+'</p>'
    +(item.note?'<small>'+esc(item.note)+'</small>':'')
    +(item.effective_at?'<small>生效于 '+esc(date(item.effective_at))+'</small>':'')
    +(item.revoked_at?'<small>撤销于 '+esc(date(item.revoked_at))+'</small>':'')
    +'</div><div class="maintenance-actions">'+actions.join('')+'</div>'
    +'<div class="maintenance-detail" id="impact-'+item.id+'"></div></article>';
}

export async function maintenancePage(){
  const list=await maintenances.list();
  workspace.maintenances=list;
  const fields='<label>检修名称<input name="name" required minlength="2" placeholder="例如：主控机房夜间检修"></label>'
    +'<label>播出链路<select name="channel"><option>新闻一频</option><option>文化二频</option><option>城市直播</option></select></label>'
    +'<label>开始时刻<input name="start_at" required placeholder="2026-08-15 23:00"></label>'
    +'<label>结束时刻<input name="end_at" required placeholder="2026-08-16 01:00"></label>'
    +'<label>备注<input name="note" maxlength="500" placeholder="可选，值班补登依据"></label>';
  const draftVisible=canWrite()?'':' disabled';
  return heading('04 / PLANNED MAINTENANCE','计划检修豁免与停播口径','按链路登记检修起止时刻，跨午夜分日扣除、重叠时段只扣一次；生效时冻结版本，关联的未批准分析转入待重算。观察员只读。')
    +'<div class="maintenance-grid"><section class="panel"><div class="section-title"><h2>登记检修（草稿）</h2><span>草稿可补登修改</span></div>'
    +'<form id="maintenance-form">'+fields+'<button type="submit" class="primary" '+draftVisible+'>保存草稿</button><p class="hint">生效与撤销由业务负责人执行，并各自产生新修订。生效会把该链路未批准的分析标记为待重算，原结果保留。</p></form></section>'
    +'<section><div class="section-title"><h2>检修记录</h2><span>'+list.length+' 条</span></div><div class="maintenance-list">'+(list.length?list.map(recordCard).join(''):'<p class="empty">尚无检修豁免。登记草稿并由负责人生效后，重算将按新版口径扣除。</p>')+'</div></section></div>'
    +(canWrite()?'':'<p class="hint">当前账号为观察员，仅可查看检修豁免与扣除前后明细。</p>');
}

export function bindMaintenance(refresh){
  const form=document.querySelector('#maintenance-form');
  if(form)submit(form,async f=>{
    const payload={name:f.get('name'),channel:f.get('channel'),start_at:f.get('start_at'),end_at:f.get('end_at'),note:f.get('note')||''};
    if(form.dataset.editing)await maintenances.update(Number(form.dataset.editing),payload);
    else await maintenances.create(payload);
    notify('检修草稿已保存');await refresh();
  });
  document.querySelectorAll('[data-edit]').forEach(button=>button.onclick=async()=>{
    try{
      const item=await maintenances.get(button.dataset.edit),form=document.querySelector('#maintenance-form');
      form.dataset.editing=item.id;
      form.querySelector('[name=name]').value=item.name;form.querySelector('[name=channel]').value=item.channel;
      form.querySelector('[name=start_at]').value=item.start_at;form.querySelector('[name=end_at]').value=item.end_at;
      form.querySelector('[name=note]').value=item.note||'';
      form.querySelector('[type=submit]').textContent='更新草稿';
      form.scrollIntoView({behavior:'smooth'});notify('已载入草稿，可补登修改');
    }catch(e){notify(e.message,true);}
  });
  document.querySelectorAll('[data-impact]').forEach(button=>button.onclick=async()=>{
    const panel=document.querySelector('#impact-'+button.dataset.impact);
    if(panel.dataset.open){panel.innerHTML='';delete panel.dataset.open;return;}
    try{
      const impact=await maintenances.impact(button.dataset.impact);
      const jobs=impact.affected_jobs||[],approved=impact.approved_jobs||[];
      panel.innerHTML=deductionTable(impact)
        +'<div class="impact-jobs"><h4>待重算分析</h4>'+(jobs.length?'<ul>'+jobs.map(j=>'<li><a href="#/results/'+j.id+'">'+esc(j.name)+'</a> · '+esc(j.status)+'</li>').join('')+'</ul>':'<p>暂无待重算分析。</p>')
        +'<h4>已批准结果</h4>'+(approved.length?'<ul>'+approved.map(j=>'<li><a href="#/results/'+j.id+'">'+esc(j.name)+'</a> · 沿用批准时检修依据（修订 '+esc(j.basis_revision??'—')+'）</li>').join('')+'</ul>':'<p>暂无已批准结果。</p>')+'</div>';
      panel.dataset.open='1';
    }catch(e){notify(e.message,true);}
  });
  document.querySelectorAll('[data-effective]').forEach(button=>button.onclick=async()=>{
    if(!confirm('生效将冻结当前检修版本，并把该链路未批准分析转为待重算。继续？'))return;
    try{const r=await maintenances.effective(button.dataset.effective);notify('已生效，影响 '+(r.affected_jobs?.length||0)+' 个待重算分析');await refresh();}catch(e){notify(e.message,true);}
  });
  document.querySelectorAll('[data-revoke]').forEach(button=>button.onclick=async()=>{
    if(!confirm('撤销会生成新修订，并使该链路未批准分析再次待重算。继续？'))return;
    try{const r=await maintenances.revoke(button.dataset.revoke);notify('已撤销，影响 '+(r.affected_jobs?.length||0)+' 个待重算分析');await refresh();}catch(e){notify(e.message,true);}
  });
}
